/* @bruin
name: staging.weekly_status_outlook
tags:
    - hourly
type: duckdb.sql

description: |
    The latest NTCSA Weekly System Status Report's 52-week adequacy outlook,
    one row per forecast week with a green/yellow/orange/red status. Feeds the
    Outlook tab's adequacy summary.

materialization:
    type: table
    strategy: create+replace

depends:
    - raw.weekly_status_outlook

columns:
    - name: report_week
      type: INTEGER
    - name: report_period
      type: VARCHAR
    - name: week_start
      type: DATE
    - name: week_num
      type: INTEGER
    - name: residual_forecast_mw
      type: INTEGER
    - name: available_less_or_ua_mw
      type: INTEGER
    - name: planned_risk_mw
      type: INTEGER
    - name: likely_risk_mw
      type: INTEGER
    - name: status
      type: VARCHAR
@bruin */

SELECT
    report_week,
    report_period,
    week_start,
    week_num,
    residual_forecast_mw,
    available_less_or_ua_mw,
    planned_risk_mw,
    likely_risk_mw,
    status
FROM raw.weekly_status_outlook
ORDER BY week_start
