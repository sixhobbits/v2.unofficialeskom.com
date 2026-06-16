"""Canonical catalogue of every graph on the Eskom Data Portal.

Single source of truth for *which* graphs exist and their stable portal page
URLs (the six sections of https://www.eskom.co.za/dataportal/). The volatile
bits — the CSV download URL and the PowerBI embed — are NOT listed here: they
change over time, so the generic scrapers (raw.portal_csv*, raw.portal_powerbi*)
re-discover them from each page on every run.

`slug` is the path after /dataportal/ and is used as the join key across the
scraper tables and the dashboard JSON.
"""

PORTAL_GRAPHS: list[dict[str, str]] = [
    {"section": "Demand side", "name": "Weekly peak demand", "slug": "demand-side/weekly-peak-demand", "page_url": "https://www.eskom.co.za/dataportal/demand-side/weekly-peak-demand/"},
    {"section": "Demand side", "name": "Weekly energy demand", "slug": "demand-side/weekly-energy-demand", "page_url": "https://www.eskom.co.za/dataportal/demand-side/weekly-energy-demand/"},
    {"section": "Demand side", "name": "System hourly actual and forecasted demand", "slug": "demand-side/system-hourly-actual-and-forecasted-demand", "page_url": "https://www.eskom.co.za/dataportal/demand-side/system-hourly-actual-and-forecasted-demand/"},
    {"section": "Demand side", "name": "System hourly demand and available capacity", "slug": "demand-side/system-hourly-demand-and-available-capacity", "page_url": "https://www.eskom.co.za/dataportal/demand-side/system-hourly-demand-and-available-capacity/"},
    {"section": "Demand side", "name": "Official hourly forecast for the next 3 months", "slug": "demand-side/official-hourly-forcast-for-next-3-months", "page_url": "https://www.eskom.co.za/dataportal/demand-side/official-hourly-forcast-for-next-3-months/"},
    {"section": "Supply side", "name": "Station build-up for the last 7 days", "slug": "supply-side/station-build-up-for-the-last-7-days", "page_url": "https://www.eskom.co.za/dataportal/supply-side/station-build-up-for-the-last-7-days/"},
    {"section": "Supply side", "name": "Station build-up for yesterday", "slug": "supply-side/station-build-up-for-yesterday", "page_url": "https://www.eskom.co.za/dataportal/supply-side/station-build-up-for-yesterday/"},
    {"section": "Supply side", "name": "Pumped storage generating hours, gas generation & manual load reduction", "slug": "supply-side/pumped-storage-generating-hours-gas-generation-and-manual-load-reduction", "page_url": "https://www.eskom.co.za/dataportal/supply-side/pumped-storage-generating-hours-gas-generation-and-manual-load-reduction/"},
    {"section": "OCGT usage", "name": "Financial year load factor (IPP OCGT)", "slug": "ocgt-usage/financial-year-load-factor-ipp-ocgt", "page_url": "https://www.eskom.co.za/dataportal/ocgt-usage/financial-year-load-factor-ipp-ocgt/"},
    {"section": "OCGT usage", "name": "Financial year load factor (Eskom OCGT)", "slug": "ocgt-usage/financial-year-load-factor-eskom-ocgt", "page_url": "https://www.eskom.co.za/dataportal/ocgt-usage/financial-year-load-factor-eskom-ocgt/"},
    {"section": "OCGT usage", "name": "Load factor last 7 days (IPP OCGT)", "slug": "ocgt-usage/load-factor-last-7-days-ipp-ocgt", "page_url": "https://www.eskom.co.za/dataportal/ocgt-usage/load-factor-last-7-days-ipp-ocgt/"},
    {"section": "OCGT usage", "name": "Load factor last 7 days (Eskom OCGT)", "slug": "ocgt-usage/load-factor-last-7-days-eskom-ocgt", "page_url": "https://www.eskom.co.za/dataportal/ocgt-usage/load-factor-last-7-days-eskom-ocgt/"},
    {"section": "OCGT usage", "name": "Total monthly OCGT (Eskom + IPP) and GT energy utilization", "slug": "ocgt-usage/total-monthly-ocgt-eskom-ipp-and-gt-energy-utilization", "page_url": "https://www.eskom.co.za/dataportal/ocgt-usage/total-monthly-ocgt-eskom-ipp-and-gt-energy-utilization/"},
    {"section": "Renewables", "name": "Hourly renewable generation", "slug": "renewables-performance/hourly-renewable-generation", "page_url": "https://www.eskom.co.za/dataportal/renewables-performance/hourly-renewable-generation/"},
    {"section": "Renewables", "name": "Total hourly renewable generation", "slug": "renewables-performance/total-hourly-renewable-generation", "page_url": "https://www.eskom.co.za/dataportal/renewables-performance/total-hourly-renewable-generation/"},
    {"section": "Renewables", "name": "Wind generation weekly load factor", "slug": "renewables-performance/wind-generation-weekly-load-factor", "page_url": "https://www.eskom.co.za/dataportal/renewables-performance/wind-generation-weekly-load-factor/"},
    {"section": "Renewables", "name": "Renewable Statistics", "slug": "renewables-performance/renewable-statistics", "page_url": "https://www.eskom.co.za/dataportal/renewables-performance/renewable-statistics/"},
    {"section": "Outages", "name": "Monthly Eskom Generation capacity breakdown", "slug": "outage-performance/monthly-eskom-generation-capacity-breakdown", "page_url": "https://www.eskom.co.za/dataportal/outage-performance/monthly-eskom-generation-capacity-breakdown/"},
    {"section": "Outages", "name": "Monthly Eskom Generation unavailability", "slug": "outage-performance/monthly-eskom-generation-unavailability", "page_url": "https://www.eskom.co.za/dataportal/outage-performance/monthly-eskom-generation-unavailability/"},
    {"section": "Outages", "name": "Weekly unplanned outages", "slug": "outage-performance/weekly-unplanned-outages", "page_url": "https://www.eskom.co.za/dataportal/outage-performance/weekly-unplanned-outages/"},
    {"section": "Outages", "name": "Weekly Eskom Generation capacity breakdown", "slug": "outage-performance/weekly-eskom-generation-capacity-breakdown", "page_url": "https://www.eskom.co.za/dataportal/outage-performance/weekly-eskom-generation-capacity-breakdown/"},
    {"section": "Outages", "name": "Weekly UCLF + OCLF Frequency", "slug": "outage-performance/weekly-uclfoclf-frequency", "page_url": "https://www.eskom.co.za/dataportal/outage-performance/weekly-uclfoclf-frequency/"},
    {"section": "Outages", "name": "Hourly UCLF + OCLF Trend", "slug": "outage-performance/hourly-uclfoclf-trend", "page_url": "https://www.eskom.co.za/dataportal/outage-performance/hourly-uclfoclf-trend/"},
    {"section": "Emissions", "name": "Atmospheric Emission License Reports", "slug": "emissions/ael", "page_url": "https://www.eskom.co.za/dataportal/emissions/ael/"},
    {"section": "Emissions", "name": "GHG Emissions", "slug": "emissions/elementor-291086", "page_url": "https://www.eskom.co.za/dataportal/emissions/elementor-291086/"},
]
