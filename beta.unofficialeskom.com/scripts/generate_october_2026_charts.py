"""Reproduce October 2026 article charts: python SCRIPT /path/to/eskom.sqlite.

Requires pandas and matplotlib. Uses source hour labels and excludes November.
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

OUT = Path(__file__).resolve().parents[1] / 'blog/2026-11-02-eskom-october-2026'
MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']


def save(fig, name):
    fig.text(.09, .035, 'Source: Eskom bulk export ESK20088 + historical base  |  unofficialeskom.com',
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
    data = data.apply(pd.to_numeric, errors='coerce').sort_index().loc[:'2026-10-31 23:00']
    assert data.index.is_unique
    data['Outages'] = data[['Total PCLF', 'Total UCLF', 'Total OCLF']].sum(axis=1, min_count=3)
    data['EAF'] = 100 * (1 - data['Outages'] / data['Installed Eskom Capacity'])
    data['OCGT'] = data['Eskom OCGT Generation'] + data['Dispatchable IPP OCGT']
    data['Renewables'] = data[['Wind', 'PV', 'CSP', 'Other RE']].sum(axis=1, min_count=4)
    october = data.loc['2026-10']
    required = ['EAF', 'Outages', 'Nuclear Generation', 'Residual Demand', 'OCGT',
                'Wind', 'PV', 'CSP', 'Other RE', 'Renewables']
    assert october.index.equals(pd.date_range('2026-10-01', '2026-10-31 23:00', freq='h'))
    assert october[required].notna().all().all()
    monthly = data.resample('MS').mean()
    OUT.mkdir(parents=True, exist_ok=True)

    eaf = monthly.loc['2026-10-01', 'EAF']
    fig, ax = figure('Availability slipped again but stayed above last October',
                      f'Derived monthly EAF  |  October 2026: {eaf:.1f}%, highest October since 2018', '% of installed Eskom capacity')
    for year, color in [(2023, '#c7ceca'), (2024, '#91a399'), (2025, BLUE), (2026, GREEN)]:
        series = monthly.loc[str(year), 'EAF']
        ax.plot(series.index.month, series, color=color, linewidth=3 if year == 2026 else 1.8,
                marker='o', markersize=3, label=str(year))
    ax.set_xticks(range(1, 13), MONTHS)
    ax.set_ylim(45, 85)
    ax.annotate(f'{eaf:.1f}%', (10, eaf), xytext=(10, -3), textcoords='offset points', color=GREEN, weight='bold')
    ax.legend(frameon=False, ncol=4, loc='lower right')
    save(fig, 'img-eaf.png')

    daily = data.loc['2026-09-15':'2026-10-31'].resample('D').agg(
        {'Total UCLF': 'mean', 'OCGT': 'max', 'Nuclear Generation': 'mean'})
    fig, ax = figure('A week of high unplanned losses around the Koeberg trip',
                      'Daily average unplanned losses (bars) and hourly OCGT peak (line)  |  Koeberg Unit 1 offline 16–22 October',
                      'GW')
    ax.bar(daily.index, daily['Total UCLF'] / 1000, color=RED, width=.8, label='Unplanned losses (daily avg)')
    ax.plot(daily.index, daily['OCGT'] / 1000, color=GOLD, linewidth=2.5, marker='o', markersize=3,
            label='Combined OCGT (daily hourly peak)')
    ax.axvspan(pd.Timestamp('2026-10-16'), pd.Timestamp('2026-10-22'), color=BLUE, alpha=.12, label='Koeberg Unit 1 offline')
    ax.set_ylim(0, 15)
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    ax.legend(frameon=False, ncol=3, loc='upper left', fontsize=9)
    save(fig, 'img-uclf-daily.png')

    recent = monthly.loc['2025':]
    total = recent['Outages'].iloc[-1] / 1000
    fig, ax = figure('Unplanned losses rose for a second month',
                      'Monthly average losses  |  September → October: unplanned +0.72 GW; planned −0.30 GW', 'GW of unavailable capacity')
    x = np.arange(len(recent)); bottom = np.zeros(len(x))
    for col, label, color in [('Total UCLF', 'Unplanned', RED), ('Total PCLF', 'Planned', GOLD), ('Total OCLF', 'Other', BLUE)]:
        values = recent[col].to_numpy() / 1000
        ax.bar(x, values, bottom=bottom, color=color, label=label, width=.72)
        bottom += values
    ticks = sorted(set(list(range(0, len(x), 2)) + [len(x)-1]))
    ax.set_xticks(ticks, [recent.index[i].strftime('%b %y') for i in ticks], fontsize=9)
    ax.set_ylim(0, 24); ax.legend(frameon=False, ncol=3, loc='upper right')
    ax.annotate(f'{total:.2f}', (x[-1], bottom[-1]), xytext=(0, 6), textcoords='offset points', ha='center', weight='bold')
    save(fig, 'img-clf.png')

    nuc = monthly.loc['2026-10-01', 'Nuclear Generation']
    fig, ax = figure('Koeberg Unit 1 tripped mid-month and returned within a week',
                      f'Hourly reported nuclear generation  |  October average: {nuc:.0f} MW; negative readings 16–20 October', 'MW, as reported in the export')
    nuclear = data.loc['2026-09-01':, 'Nuclear Generation']
    ax.plot(nuclear.index, nuclear, color=GREEN, linewidth=1.5)
    ax.axhline(0, color='#89948c', linewidth=1)
    ax.axvline(pd.Timestamp('2026-10-01'), color=BLUE, linestyle='--', linewidth=1)
    ax.set_ylim(-90, 820); ax.set_xlim(pd.Timestamp('2026-09-01'), pd.Timestamp('2026-11-01'))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    save(fig, 'img-nuclear.png')

    history = monthly[monthly.index.month == 10]
    dem = history['Residual Demand']
    fig, ax = figure('October residual demand hit a new low',
                      f'Average October residual demand  |  2026: {dem.iloc[-1]:,.0f} MW, down {100*(1-dem.iloc[-1]/dem.iloc[-2]):.1f}% year on year',
                      'Average residual demand, GW')
    values = dem / 1000
    ax.bar(history.index.year, values, color=[GREEN if y == 2026 else '#a9bbae' for y in history.index.year])
    ax.set_xticks(history.index.year); ax.set_ylim(0, 30)
    for year, value in zip(history.index.year, values):
        ax.text(year, value+.4, f'{value:.1f}', ha='center', fontsize=10)
    save(fig, 'img-demand.png')

    current = monthly.loc['2026']; peak = data['OCGT'].resample('MS').max().loc['2026']
    fig, ax = figure('Diesel use rose, with the highest hourly peak of 2026',
                      f'Combined Eskom + IPP OCGT output  |  October average: {current["OCGT"].iloc[-1]:.0f} MW; hourly peak: {peak.iloc[-1]:,.0f} MW', 'MW')
    x = np.arange(len(current))
    ax.bar(x, current['OCGT'], color=RED, width=.5, label='Monthly average')
    ax.plot(x, peak, color=GOLD, linewidth=2.5, marker='o', label='Hourly peak')
    ax.set_xticks(x, current.index.strftime('%b')); ax.set_ylim(0, 3300)
    ax.legend(frameon=False, loc='upper left')
    ax.annotate(f'{peak.iloc[-1]:,.0f}', (x[-1], peak.iloc[-1]), xytext=(0, 10), textcoords='offset points', ha='center', weight='bold')
    save(fig, 'img-ocgt.png')

    hist = history.loc['2021':]
    re_now, re_prev = hist['Renewables'].iloc[-1], hist['Renewables'].iloc[-2]
    fig, ax = figure('A weak wind month pulled renewables down',
                      f'Average October generation  |  Combined renewables: {re_now:,.0f} MW, down {100*(1-re_now/re_prev):.1f}% year on year',
                      'Average generation, MW')
    x = np.arange(len(hist)); bottom = np.zeros(len(hist))
    for col, label, color in [('Wind','Wind',BLUE), ('PV','PV',GOLD), ('CSP','CSP',GREEN), ('Other RE','Other','#a7b2ac')]:
        values = hist[col].to_numpy()
        ax.bar(x, values, bottom=bottom, color=color, label=label, width=.6)
        bottom += values
    ax.set_xticks(x, hist.index.year); ax.set_ylim(0, 2700)
    ax.legend(frameon=False, ncol=4, loc='upper left')
    for i, t in enumerate(bottom):
        ax.text(i, t+45, f'{t:,.0f}', ha='center', fontsize=10)
    save(fig, 'img-renewables.png')
    print(monthly.loc[['2025-10-01', '2026-09-01', '2026-10-01'], required].round(1).T.to_string())
    print(f'Wrote seven charts to {OUT}')


if __name__ == '__main__':
    main()
