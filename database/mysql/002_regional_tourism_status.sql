-- 지역별 관광 현황 일괄 다운로드의 관측 근거를 저장한다.
-- 기존 fact_tourism_monthly/ML target과 섞지 않는다. 유입·유출/인기 장소는
-- 기획 후보와 운영 범위의 보조 사실, 집중률은 향후 30일 운영 참고 신호다.

CREATE TABLE IF NOT EXISTS regional_tourism_status_flow (
    region_code VARCHAR(10) NOT NULL,
    source_period VARCHAR(30) NOT NULL,
    direction VARCHAR(12) NOT NULL,
    related_region_name VARCHAR(150) NOT NULL,
    ratio_pct DECIMAL(10,4) NOT NULL,
    rank_no SMALLINT UNSIGNED NOT NULL,
    source_id VARCHAR(80) NOT NULL,
    PRIMARY KEY (region_code, source_period, direction, related_region_name, source_id),
    CONSTRAINT fk_status_flow_region FOREIGN KEY (region_code) REFERENCES dim_region(region_code),
    CONSTRAINT fk_status_flow_source FOREIGN KEY (source_id) REFERENCES data_source(source_id),
    CHECK (direction IN ('inbound', 'outbound')),
    KEY ix_status_flow_region_period (region_code, source_period, direction, rank_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS regional_tourism_status_flow_category (
    region_code VARCHAR(10) NOT NULL,
    source_period VARCHAR(30) NOT NULL,
    direction VARCHAR(12) NOT NULL,
    dataset_type VARCHAR(40) NOT NULL,
    category_group VARCHAR(150) NOT NULL,
    category_detail VARCHAR(150) NOT NULL DEFAULT '',
    share_pct DECIMAL(10,4) NOT NULL,
    group_share_pct DECIMAL(10,4) NULL,
    source_id VARCHAR(80) NOT NULL,
    PRIMARY KEY (region_code, source_period, direction, dataset_type, category_group, category_detail, source_id),
    CONSTRAINT fk_status_flow_category_region FOREIGN KEY (region_code) REFERENCES dim_region(region_code),
    CONSTRAINT fk_status_flow_category_source FOREIGN KEY (source_id) REFERENCES data_source(source_id),
    CHECK (direction IN ('inbound', 'outbound')),
    KEY ix_status_flow_category_region_period (region_code, source_period, dataset_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS regional_tourism_status_place (
    region_code VARCHAR(10) NOT NULL,
    source_period VARCHAR(30) NOT NULL,
    dataset_type VARCHAR(50) NOT NULL,
    audience VARCHAR(20) NOT NULL,
    language VARCHAR(40) NOT NULL DEFAULT '',
    place_id VARCHAR(100) NOT NULL DEFAULT '',
    place_name VARCHAR(250) NOT NULL,
    classification VARCHAR(150) NOT NULL DEFAULT '',
    rank_no SMALLINT UNSIGNED NULL,
    -- 순위형 원본에는 월 값이 없으므로 NULL 대신 빈 문자열을 자연키에 보존한다.
    observation_month CHAR(7) NOT NULL DEFAULT '',
    metric_name VARCHAR(40) NOT NULL,
    metric_value DECIMAL(22,4) NULL,
    metric_unit VARCHAR(30) NOT NULL,
    source_id VARCHAR(80) NOT NULL,
    PRIMARY KEY (region_code, source_period, dataset_type, audience, language, place_id, place_name, observation_month, source_id),
    CONSTRAINT fk_status_place_region FOREIGN KEY (region_code) REFERENCES dim_region(region_code),
    CONSTRAINT fk_status_place_source FOREIGN KEY (source_id) REFERENCES data_source(source_id),
    KEY ix_status_place_region_period (region_code, source_period, dataset_type, audience, rank_no),
    KEY ix_status_place_observation_month (observation_month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS regional_tourism_status_concentration (
    region_code VARCHAR(10) NOT NULL,
    signal_date DATE NOT NULL,
    visit_ratio_pct DECIMAL(10,4) NOT NULL,
    source_id VARCHAR(80) NOT NULL,
    PRIMARY KEY (region_code, signal_date, source_id),
    CONSTRAINT fk_status_concentration_region FOREIGN KEY (region_code) REFERENCES dim_region(region_code),
    CONSTRAINT fk_status_concentration_source FOREIGN KEY (source_id) REFERENCES data_source(source_id),
    KEY ix_status_concentration_region_date (region_code, signal_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
