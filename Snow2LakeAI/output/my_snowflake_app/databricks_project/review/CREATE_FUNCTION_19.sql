RAW_SQL RAW_SQL -- â”€â”€ UDF: CONTRACT CLASS DETECTOR (12 categories) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
CREATE OR REPLACE FUNCTION app.detect_contract_class(
    contract_type STRING, industry STRING, contract_text STRING
)
RETURNS STRING LANGUAGE SQL AS
$$
    CASE
        WHEN CONTAINS(LOWER(COALESCE(contract_type,'')), 'insurance')
          OR CONTAINS(LOWER(COALESCE(contract_text,'')), 'premium')
          OR CONTAINS(LOWER(COALESCE(contract_text,'')), 'policyholder')
        THEN 'Insurance'
        WHEN CONTAINS(LOWER(COALESCE(contract_type,'')), 'nda')
          OR CONTAINS(LOWER(COALESCE(contract_type,'')), 'non-disclosure')
        THEN 'NDA'
        WHEN CONTAINS(LOWER(COALESCE(contract_type,'')), 'employment')
          OR CONTAINS(LOWER(COALESCE(contract_type,'')), 'offer letter')
        THEN 'Employment'
        WHEN CONTAINS(LOWER(COALESCE(contract_type,'')), 'lease')
          OR CONTAINS(LOWER(COALESCE(contract_text,'')), 'landlord')
        THEN 'Lease'
        WHEN CONTAINS(LOWER(COALESCE(contract_type,'')), 'government')
          OR CONTAINS(LOWER(COALESCE(contract_text,'')), 'federal')
        THEN 'Government'
        WHEN CONTAINS(LOWER(COALESCE(contract_type,'')), 'procurement')
          OR CONTAINS(LOWER(COALESCE(contract_type,'')), 'purchase order')
        THEN 'Procurement'
        WHEN CONTAINS(LOWER(COALESCE(industry,'')), 'healthcare')
          OR CONTAINS(LOWER(COALESCE(contract_text,'')), 'hipaa')
        THEN 'Healthcare'
        WHEN CONTAINS(LOWER(COALESCE(industry,'')), 'financial')
          OR CONTAINS(LOWER(COALESCE(contract_text,'')), 'fiduciary')
        THEN 'Financial Services'
        WHEN CONTAINS(LOWER(COALESCE(contract_type,'')), 'saas')
          OR CONTAINS(LOWER(COALESCE(contract_type,'')), 'subscription')
        THEN 'SaaS'
        WHEN CONTAINS(LOWER(COALESCE(industry,'')), 'telecom')
          OR CONTAINS(LOWER(COALESCE(contract_text,'')), 'bandwidth')
        THEN 'Telecom'
        WHEN CONTAINS(LOWER(COALESCE(industry,'')), 'manufacturing')
          OR CONTAINS(LOWER(COALESCE(contract_text,'')), 'supply chain')
        THEN 'Manufacturing'
        ELSE 'Vendor'
    END
$$