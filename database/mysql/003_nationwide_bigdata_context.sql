-- 전국 빅데이터 다운로드의 기간 합계/비중과 전국 월별 맥락을 별도 보조 근거로 저장한다.
-- 이 표들은 fact_tourism_monthly·ML target과 섞지 않는다.

CREATE TABLE IF NOT EXISTS nationwide_municipal_period_metric (
    region_code VARCHAR(10) NOT NULL,
    metric_name VARCHAR(80) NOT NULL,
    audience VARCHAR(20) NOT NULL,
    dataset_group VARCHAR(30) NOT NULL,
    period_start CHAR(7) NOT NULL,
    period_end CHAR(7) NOT NULL,
    period_kind VARCHAR(30) NOT NULL,
    metric_value DECIMAL(28,4) NULL,
    unit VARCHAR(30) NOT NULL,
    share_pct DECIMAL(12,6) NULL,
    source_id VARCHAR(80) NOT NULL,
    source_row_number INT UNSIGNED NOT NULL,
    PRIMARY KEY (region_code, metric_name, audience, period_start, period_end, source_id),
    CONSTRAINT fk_bigdata_period_region FOREIGN KEY (region_code) REFERENCES dim_region(region_code),
    CONSTRAINT fk_bigdata_period_source FOREIGN KEY (source_id) REFERENCES data_source(source_id),
    CHECK (period_start REGEXP '^20[0-9]{2}-(0[1-9]|1[0-2])$'),
    CHECK (period_end REGEXP '^20[0-9]{2}-(0[1-9]|1[0-2])$'),
    CHECK (period_kind IN ('annual', 'partial_period')),
    KEY ix_bigdata_period_region (region_code, period_end),
    KEY ix_bigdata_period_metric (metric_name, audience, period_end)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS nationwide_monthly_tourism_context (
    `year_month` CHAR(7) NOT NULL,
    metric_name VARCHAR(80) NOT NULL,
    audience VARCHAR(20) NOT NULL,
    dataset_group VARCHAR(30) NOT NULL,
    category_name VARCHAR(150) NOT NULL,
    metric_value DECIMAL(28,4) NOT NULL,
    unit VARCHAR(30) NOT NULL,
    source_id VARCHAR(80) NOT NULL,
    source_row_number INT UNSIGNED NOT NULL,
    PRIMARY KEY (`year_month`, metric_name, audience, category_name, source_id),
    CONSTRAINT fk_bigdata_monthly_source FOREIGN KEY (source_id) REFERENCES data_source(source_id),
    CHECK (`year_month` REGEXP '^20[0-9]{2}-(0[1-9]|1[0-2])$'),
    KEY ix_bigdata_monthly_metric (`year_month`, metric_name, audience)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
