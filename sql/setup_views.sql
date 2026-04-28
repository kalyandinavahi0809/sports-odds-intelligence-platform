-- DuckDB view definitions for normalized odds

CREATE OR REPLACE VIEW vw_odds AS
SELECT * FROM read_parquet('data/processed/odds.parquet');
