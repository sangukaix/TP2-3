CREATE TABLE IF NOT EXISTS festival_case_catalog (
    dataset_hash CHAR(64) NOT NULL,
    festival_id VARCHAR(64) NOT NULL,
    region_code VARCHAR(10) NULL,
    festival_name VARCHAR(150) NOT NULL,
    payload_json JSON NOT NULL,
    imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (dataset_hash, festival_id),
    INDEX idx_festival_region (region_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
