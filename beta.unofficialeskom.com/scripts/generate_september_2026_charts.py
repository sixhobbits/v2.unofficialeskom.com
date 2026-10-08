"""Reproduce September 2026 article charts: python SCRIPT /path/to/eskom.sqlite.

Requires pandas and matplotlib. Uses source hour labels and excludes October.
"""
import argparse
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

from generate_august_2026_charts import figure, GREEN, RED, GOLD, BLUE

OUT = Path(__file__).resolve().parents[1] / 'blog/2026-10-08-eskom-september-2026'


def save(fig, name):
    fig.text(.09, .035, 'Source: Eskom bulk export ESK19908 + historical base  |  unofficialeskom.com',
             fontsize=9, color='#65766a')
    fig.savefig(OUT / name, dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sqlite', type=Path)
    args = parser.parse_args()
    with sqlite3.connect(args.sqlite) as conn:
        data = pd.read_sql('SELECT * FROM eskom', conn)
    data.index = pd.to_datetime(data.pop('Date Time Hour Beginning'), format='%Y-%m-%d %I:%M:%S %p')
    data = data.apply(pd.to_numeric, errors='coerce').sort_index().loc[:'2026-09-30 23:00']
    assert data.index.is_unique
    data['Outages'] = data[['Total PCLF', 'Total UCLF', 'Total OCLF']].sum(axis=1, min_count=3)
    data['EAF'] = 100 * (1 - data['Outages'] / data['Installed Eskom Capacity'])
    data['OCGT'] = data['Eskom OCGT Generation'] + data['Dispatchable IPP OCGT']
    data['Renewables'] = data[['Wind', 'PV', 'CSP', 'Other RE']].sum(axis=1, min_count=4)
    september = data.loc['2026-09']
    required = ['EAF', 'Outages', 'Nuclear Generation', 'Residual Demand', 'OCGT',
                'Wind', 'PV', 'CSP', 'Other RE', 'Renewables']
    assert september.index.equals(pd.date_range('2026-09-01', '2026-09-30 23:00', freq='h'))
    assert september[required].notna().all().all()
    monthly = data.resample('MS').mean()
    OUT.mkdir(parents=True, exist_ok=True)

    fig, ax = figure('Availability fell as unplanned outages rose',
                      'Derived monthly EAF  |  September 2026: 69.5%, down 1.5 points from August', '% of installed Eskom capacity')
    for year, color in [(2023, '#c7ceca'), (2024, '#91a399'), (2025, BLUE), (2026, GREEN)]:
        series = monthly.loc[str(year), 'EAF']
        ax.plot(series.index.month, series, color=color, linewidth=3 if year == 2026 else 1.8,
                marker='o', markersize=3, label=str(year))
    ax.set_xticks(range(1, 13), ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'])
    ax.set_ylim(45, 85)
    ax.annotate('69.5%', (9, monthly.loc['2026-09-01', 'EAF']), xytext=(10, -3),
                textcoords='offset points', color=GREEN, weight='bold')
    ax.legend(frameon=False, ncol=4, loc='lower right')
    save(fig, 'img-eaf.png')

    recent = monthly.loc['2025':]
    fig, ax = figure('Unplanned losses reversed their recent improvement',
                      'Monthly average losses  |  August → September: unplanned +1.21 GW; planned −0.04 GW', 'GW of unavailable capacity')
    x = np.arange(len(recent)); bottom = np.zeros(len(x))
    for col, label, color in [('Total UCLF', 'Unplanned', RED), ('Total PCLF', 'Planned', GOLD), ('Total OCLF', 'Other', BLUE)]:
        values = recent[col].to_numpy() / 1000
        ax.bar(x, values, bottom=bottom, color=color, label=label, width=.72)
        bottom += values
    ticks = sorted(set(list(range(0, len(x), 2)) + [len(x)-1]))
    ax.set_xticks(ticks, [recent.index[i].strftime('%b %y') for i in ticks], fontsize=9)
    ax.set_ylim(0, 24); ax.legend(frameon=False, ncol=3, loc='upper right')
    ax.annotate('14.78', (x[-1], bottom[-1]), xytext=(0, 6), textcoords='offset points', ha='center', weight='bold')
    save(fig, 'img-clf.png')

    fig, ax = figure('Nuclear output stabilised after the August interruption',
                      'Hourly reported nuclear generation  |  September average: 653 MW; all readings 650–655 MW (rounded)', 'MW, as reported in the export')
    nuclear = data.loc['2026-08-01':, 'Nuclear Generation']
    ax.plot(nuclear.index, nuclear, color=GREEN, linewidth=1.5)
    ax.axhline(0, color='#89948c', linewidth=1)
    ax.axvline(pd.Timestamp('2026-09-01'), color=BLUE, linestyle='--', linewidth=1)
    ax.set_ylim(-90, 820); ax.set_xlim(pd.Timestamp('2026-08-01'), pd.Timestamp('2026-10-01'))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    save(fig, 'img-nuclear.png')

    history = monthly[monthly.index.month == 9]
    fig, ax = figure('September residual demand fell below 20 GW on average',
                      'Average September residual demand  |  2026: 19,991 MW, down 5.4% year on year', 'Average residual demand, GW')
    values = history['Residual Demand'] / 1000
    ax.bar(history.index.year, values, color=[GREEN if y == 2026 else '#a9bbae' for y in history.index.year])
    ax.set_xticks(history.index.year); ax.set_ylim(0, 30)
    for year, value in zip(history.index.year, values):
        ax.text(year, value+.4, f'{value:.1f}', ha='center', fontsize=10)
    save(fig, 'img-demand.png')

    current = monthly.loc['2026']; peak = data['OCGT'].resample('MS').max().loc['2026']
    fig, ax = figure('Diesel use eased from August but exceeded September 2025',
                      'Combined Eskom + IPP OCGT output  |  September average: 164 MW; hourly peak: 2,173 MW', 'MW')
    x = np.arange(len(current))
    ax.bar(x, current['OCGT'], color=RED, width=.5, label='Monthly average')
    ax.plot(x, peak, color=GOLD, linewidth=2.5, marker='o', label='Hourly peak')
    ax.set_xticks(x, current.index.strftime('%b')); ax.set_ylim(0, 3300)
    ax.legend(frameon=False, loc='upper left')
    ax.annotate('2,173', (8, peak.iloc[-1]), xytext=(0, 10), textcoords='offset points', ha='center', weight='bold')
    save(fig, 'img-ocgt.png')

    hist = history.loc['2021':]
    fig, ax = figure('Wind lifted renewables while both solar series fell',
                      'Average September generation  |  Combined renewables: 2,081 MW, up 4.5% year on year', 'Average generation, MW')
    x = np.arange(len(hist)); bottom = np.zeros(len(hist))
    for col, label, color in [('Wind','Wind',BLUE), ('PV','PV',GOLD), ('CSP','CSP',GREEN), ('Other RE','Other','#a7b2ac')]:
        values = hist[col].to_numpy()
        ax.bar(x, values, bottom=bottom, color=color, label=label, width=.6)
        bottom += values
    ax.set_xticks(x, hist.index.year); ax.set_ylim(0, 2700)
    ax.legend(frameon=False, ncol=4, loc='upper left')
    for i, total in enumerate(bottom):
        ax.text(i, total+45, f'{total:,.0f}', ha='center', fontsize=10)
    save(fig, 'img-renewables.png')
    print(monthly.loc[['2025-09-01', '2026-08-01', '2026-09-01'], required].to_string())
    print(f'Wrote six charts to {OUT}')


if __name__ == '__main__':
    main()
