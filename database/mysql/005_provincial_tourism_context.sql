-- 상위 시도 관측 맥락 전용. 시군구 fact/model/catalog와 분리한다.
CREATE TABLE IF NOT EXISTS provincial_tourism_monthly_context (
    province_code CHAR(2) NOT NULL,
    province_name VARCHAR(50) NOT NULL,
    `year_month` CHAR(6) NOT NULL,
    metric_name VARCHAR(40) NOT NULL,
    metric_value DECIMAL(24,4) NOT NULL,
    unit VARCHAR(20) NOT NULL,
    source_id VARCHAR(80) NOT NULL,
    source_file VARCHAR(500) NOT NULL,
    source_member VARCHAR(200) NOT NULL,
    source_sha256 CHAR(64) NOT NULL,
    source_row_number INT NOT NULL,
    PRIMARY KEY (province_code, `year_month`, metric_name)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
