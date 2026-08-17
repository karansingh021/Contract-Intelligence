-- Rule engine: 6 leakage detection rules with dynamic table routing
-- Co-authored with CoCo

CREATE OR REPLACE PROCEDURE app.run_leakage_detection()
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    data_mode    STRING;
    contracts_tbl STRING;
    customers_tbl STRING;
    billing_tbl  STRING;
    events_tbl   STRING;
    n_leakage    INTEGER DEFAULT 0;
    n_alerts     INTEGER DEFAULT 0;
    n_credits    INTEGER DEFAULT 0;
BEGIN
    SELECT setting_value INTO :data_mode
        FROM config.app_settings WHERE setting_key='DATA_MODE';

    IF (data_mode = 'CONSUMER') THEN
        contracts_tbl := 'raw.consumer_master_contracts';
        customers_tbl := 'raw.consumer_customers_local';
        billing_tbl  := 'raw.consumer_billing_local';
        events_tbl   := 'raw.consumer_events_local';

        -- Enrich CUSTOMER_ID in contracts from CRM by matching customer name
        UPDATE raw.consumer_master_contracts mc
        SET CUSTOMER_ID = cu.CUSTOMER_ID
        FROM raw.consumer_customers_local cu
        WHERE (mc.CUSTOMER_ID IS NULL OR mc.CUSTOMER_ID = '')
          AND UPPER(TRIM(mc.CUSTOMER_NAME)) = UPPER(TRIM(cu.CUSTOMER_NAME));
    ELSE
        contracts_tbl := 'raw.demo_contracts';
        customers_tbl := 'raw.demo_customers';
        billing_tbl  := 'raw.demo_billing_transactions';
        events_tbl   := 'raw.demo_operational_events';
    END IF;

    -- Clear only the current mode's data (preserve other mode's results)
    DELETE FROM analytics.credit_notes WHERE leakage_id IN
        (SELECT leakage_id FROM analytics.leakage_events WHERE data_mode = :data_mode);
    DELETE FROM analytics.alert_log WHERE leakage_id IN
        (SELECT leakage_id FROM analytics.leakage_events WHERE data_mode = :data_mode);
    DELETE FROM analytics.leakage_events WHERE data_mode = :data_mode;

    -- R01: SLA Turnaround Breach
    EXECUTE IMMEDIATE
    'INSERT INTO analytics.leakage_events
        (rule_id,rule_name,event_ref,contract_id,customer_id,customer_name,
         industry,leakage_type,leakage_amount_usd,severity,event_date,
         calculation_detail,data_mode)
     SELECT
        ''R01'', ''SLA Breach — Penalty Due'', e.event_id, e.contract_id,
        c.customer_id, cu.customer_name, cu.industry,
        ''SLA_BREACH'',
        ROUND(e.reported_value * (c.penalty_pct/100), 2),
        CASE WHEN e.reported_value * (c.penalty_pct/100) > 100000 THEN ''CRITICAL''
             WHEN e.reported_value * (c.penalty_pct/100) > 10000 THEN ''HIGH''
             WHEN e.reported_value * (c.penalty_pct/100) > 500 THEN ''MEDIUM''
             ELSE ''LOW'' END,
        e.event_date,
        ''TAT '' || e.turnaround_hours || '' hrs > SLA '' || c.sla_hours || '' hrs. Penalty = $'' || e.reported_value || '' x '' || c.penalty_pct || ''%'',
        ''' || data_mode || '''
     FROM ' || events_tbl || ' e
     JOIN ' || contracts_tbl || ' c ON c.contract_id = e.contract_id
     JOIN ' || customers_tbl || ' cu ON cu.customer_id = c.customer_id
     WHERE e.turnaround_hours IS NOT NULL AND c.sla_hours IS NOT NULL
       AND c.penalty_pct IS NOT NULL AND e.turnaround_hours > c.sla_hours
       AND e.reported_value > 0';

    -- R02: Q4 Bonus Unclaimed
    EXECUTE IMMEDIATE
    'INSERT INTO analytics.leakage_events
        (rule_id,rule_name,event_ref,contract_id,customer_id,customer_name,
         industry,leakage_type,leakage_amount_usd,severity,event_date,
         calculation_detail,data_mode)
     SELECT
        ''R02'', ''Q4 Bonus — Unclaimed'', e.event_id, e.contract_id,
        c.customer_id, cu.customer_name, cu.industry,
        ''BONUS_UNCLAIMED'',
        ROUND(e.reported_value * (c.bonus_pct/100), 2),
        ''LOW'', e.event_date,
        ''TAT '' || e.turnaround_hours || '' hrs < threshold '' || c.bonus_threshold_hrs || '' hrs. Bonus = $'' || e.reported_value || '' x '' || c.bonus_pct || ''%'',
        ''' || data_mode || '''
     FROM ' || events_tbl || ' e
     JOIN ' || contracts_tbl || ' c ON c.contract_id = e.contract_id
     JOIN ' || customers_tbl || ' cu ON cu.customer_id = c.customer_id
     WHERE e.turnaround_hours IS NOT NULL AND c.bonus_pct IS NOT NULL
       AND c.bonus_threshold_hrs IS NOT NULL
       AND e.turnaround_hours < c.bonus_threshold_hrs
       AND MONTH(e.event_date) IN (10, 11, 12)
       AND e.reported_value > 0';

    -- R03: Billing Mismatch
    EXECUTE IMMEDIATE
    'INSERT INTO analytics.leakage_events
        (rule_id,rule_name,event_ref,contract_id,customer_id,customer_name,
         industry,leakage_type,leakage_amount_usd,severity,event_date,
         calculation_detail,data_mode)
     SELECT
        ''R03'', ''Billing Mismatch'', b.transaction_id, b.contract_id,
        b.customer_id, cu.customer_name, cu.industry,
        ''BILLING_MISMATCH'',
        ABS(b.billed_amount - ROUND(b.quantity * c.unit_rate_usd, 2)),
        CASE WHEN ABS(b.billed_amount - ROUND(b.quantity * c.unit_rate_usd, 2)) > 100000 THEN ''CRITICAL''
             WHEN ABS(b.billed_amount - ROUND(b.quantity * c.unit_rate_usd, 2)) > 10000 THEN ''HIGH''
             WHEN ABS(b.billed_amount - ROUND(b.quantity * c.unit_rate_usd, 2)) > 500 THEN ''MEDIUM''
             ELSE ''LOW'' END,
        b.transaction_date,
        ''Billed $'' || b.billed_amount || '' vs expected $'' || ROUND(b.quantity * c.unit_rate_usd, 2) || '' (qty '' || b.quantity || '' x rate $'' || c.unit_rate_usd || '')'',
        ''' || data_mode || '''
     FROM ' || billing_tbl || ' b
     JOIN ' || contracts_tbl || ' c ON c.contract_id = b.contract_id
     JOIN ' || customers_tbl || ' cu ON cu.customer_id = b.customer_id
     WHERE c.unit_rate_usd IS NOT NULL AND b.quantity IS NOT NULL
       AND ABS(b.billed_amount - ROUND(b.quantity * c.unit_rate_usd, 2)) > 0.01';

    -- R04: Overage Unbilled
    EXECUTE IMMEDIATE
    'INSERT INTO analytics.leakage_events
        (rule_id,rule_name,event_ref,contract_id,customer_id,customer_name,
         industry,leakage_type,leakage_amount_usd,severity,event_date,
         calculation_detail,data_mode)
     SELECT
        ''R04'', ''Overage Unbilled'', e.event_id, e.contract_id,
        c.customer_id, cu.customer_name, cu.industry,
        ''OVERAGE_UNBILLED'',
        ROUND(e.overage_units * c.overage_rate_usd, 2),
        CASE WHEN e.overage_units * c.overage_rate_usd >= 50000 THEN ''CRITICAL''
             WHEN e.overage_units * c.overage_rate_usd >= 10000 THEN ''HIGH''
             ELSE ''MEDIUM'' END,
        e.event_date,
        ''Overage: '' || e.overage_units || '' units x $'' || c.overage_rate_usd || ''/unit'',
        ''' || data_mode || '''
     FROM ' || events_tbl || ' e
     JOIN ' || contracts_tbl || ' c ON c.contract_id = e.contract_id
     JOIN ' || customers_tbl || ' cu ON cu.customer_id = c.customer_id
     WHERE e.overage_units IS NOT NULL AND e.overage_units > 0
       AND c.overage_rate_usd IS NOT NULL AND c.overage_rate_usd > 0';

    -- R05: Delivery SLA Breach
    EXECUTE IMMEDIATE
    'INSERT INTO analytics.leakage_events
        (rule_id,rule_name,event_ref,contract_id,customer_id,customer_name,
         industry,leakage_type,leakage_amount_usd,severity,event_date,
         calculation_detail,data_mode)
     SELECT
        ''R05'', ''Delivery SLA Breach'', e.event_id, e.contract_id,
        c.customer_id, cu.customer_name, cu.industry,
        ''DELIVERY_SLA_BREACH'',
        ROUND(c.annual_value_usd * ((c.delivery_sla_pct - e.delivery_pct)/100) * (c.penalty_pct/100), 2),
        ''MEDIUM'', e.event_date,
        ''Delivery '' || e.delivery_pct || ''% < SLA '' || c.delivery_sla_pct || ''%. Penalty on shortfall.'',
        ''' || data_mode || '''
     FROM ' || events_tbl || ' e
     JOIN ' || contracts_tbl || ' c ON c.contract_id = e.contract_id
     JOIN ' || customers_tbl || ' cu ON cu.customer_id = c.customer_id
     WHERE e.delivery_pct IS NOT NULL AND c.delivery_sla_pct IS NOT NULL
       AND e.delivery_pct < c.delivery_sla_pct AND c.penalty_pct IS NOT NULL';

    -- R06: Defect Rate Breach
    EXECUTE IMMEDIATE
    'INSERT INTO analytics.leakage_events
        (rule_id,rule_name,event_ref,contract_id,customer_id,customer_name,
         industry,leakage_type,leakage_amount_usd,severity,event_date,
         calculation_detail,data_mode)
     SELECT
        ''R06'', ''Defect Rate Breach'', e.event_id, e.contract_id,
        c.customer_id, cu.customer_name, cu.industry,
        ''DEFECT_BREACH'',
        ROUND(c.annual_value_usd * (e.defect_pct/100) * (c.penalty_pct/100), 2),
        ''MEDIUM'', e.event_date,
        ''Defect rate '' || e.defect_pct || ''% > 0%. Quality penalty applied.'',
        ''' || data_mode || '''
     FROM ' || events_tbl || ' e
     JOIN ' || contracts_tbl || ' c ON c.contract_id = e.contract_id
     JOIN ' || customers_tbl || ' cu ON cu.customer_id = c.customer_id
     WHERE e.defect_pct IS NOT NULL AND e.defect_pct > 0
       AND c.defect_sla_pct IS NOT NULL AND c.penalty_pct IS NOT NULL';

    -- Generate alerts from HIGH/CRITICAL leakage
    INSERT INTO analytics.alert_log (leakage_id, contract_id, customer_name, alert_type, severity, leakage_amount_usd, alert_message)
    SELECT leakage_id, contract_id, customer_name, leakage_type, severity, leakage_amount_usd,
        rule_name || ': ' || calculation_detail
    FROM analytics.leakage_events
    WHERE severity IN ('HIGH', 'CRITICAL');

    -- Generate credit notes from HIGH/CRITICAL leakage
    INSERT INTO analytics.credit_notes (leakage_id, contract_id, customer_name, credit_type, credit_amount_usd, justification)
    SELECT leakage_id, contract_id, customer_name,
        CASE WHEN leakage_type = 'SLA_BREACH' THEN 'PENALTY_CREDIT'
             WHEN leakage_type = 'BILLING_MISMATCH' THEN 'BILLING_ADJUSTMENT'
             WHEN leakage_type = 'BONUS_UNCLAIMED' THEN 'BONUS_PAYMENT'
             ELSE 'GENERAL_CREDIT' END,
        leakage_amount_usd,
        rule_name || ': ' || calculation_detail
    FROM analytics.leakage_events
    WHERE severity IN ('HIGH', 'CRITICAL');

    SELECT COUNT(*) INTO :n_leakage FROM analytics.leakage_events;
    SELECT COUNT(*) INTO :n_alerts FROM analytics.alert_log;
    SELECT COUNT(*) INTO :n_credits FROM analytics.credit_notes;

    RETURN 'Detection complete: ' || n_leakage || ' leakage events, '
        || n_alerts || ' alerts, ' || n_credits || ' credit notes.';
END;
$$;

GRANT USAGE ON PROCEDURE app.run_leakage_detection() TO APPLICATION ROLE app_admin;
