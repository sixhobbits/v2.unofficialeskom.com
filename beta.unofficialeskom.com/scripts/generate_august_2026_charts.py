"""Reproduce the August 2026 article charts from the monthly bulk SQLite import.

Requires pandas and matplotlib. Usage:
    python generate_august_2026_charts.py /path/to/eskom.sqlite

Uses source timestamps directly, before warehouse timezone conversion. Filters
out data after August so subsequent monthly imports do not extend the charts.
"""
from pathlib import Path
import argparse
import sqlite3

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter
import pandas as pd
import numpy as np

OUT = Path(__file__).resolve().parents[1] / 'blog/2026-09-09-eskom-august-2026'
GREEN, RED, GOLD, BLUE = '#269651', '#d65d65', '#e5ae25', '#4787ba'
INK, GRAY = '#23352b', '#89948c'
plt.rcParams.update({
    'font.family': 'DejaVu Sans', 'font.size': 11,
    'text.color': INK, 'axes.labelcolor': INK, 'xtick.color': INK,
    'ytick.color': INK, 'axes.spines.top': False, 'axes.spines.right': False,
    'axes.spines.left': False, 'axes.spines.bottom': False,
    'axes.titleweight': 'bold', 'axes.titlesize': 17,
    'axes.axisbelow': True, 'savefig.facecolor': 'white',
})


def figure(title, subtitle, ylabel):
    fig, ax = plt.subplots(figsize=(11, 5.8))
    fig.subplots_adjust(left=.09, right=.965, top=.77, bottom=.17)
    fig.text(.09, .93, title, fontsize=18, weight='bold')
    fig.text(.09, .865, subtitle, fontsize=11, color='#57685d')
    ax.set_ylabel(ylabel, labelpad=12)
    ax.grid(axis='y', color='#e6ece7', linewidth=.8)
    ax.tick_params(length=0, pad=8)
    return fig, ax


def save(fig, name):
    fig.text(.09, .035, 'Source: Eskom bulk export ESK19715 + historical base  |  unofficialeskom.com',
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
    data = data.apply(pd.to_numeric, errors='coerce').sort_index().loc[:'2026-08-31 23:00:00']
    assert data.index.is_unique
    data['Outages'] = data[['Total PCLF', 'Total UCLF', 'Total OCLF']].sum(axis=1, min_count=3)
    data['EAF'] = 100 * (1 - data['Outages'] / data['Installed Eskom Capacity'])
    data['OCGT'] = data['Eskom OCGT Generation'] + data['Dispatchable IPP OCGT']
    data['Renewables'] = data[['Wind', 'PV', 'CSP', 'Other RE']].sum(axis=1, min_count=4)
    august = data.loc['2026-08']
    assert len(august) == 744
    required = ['EAF', 'Outages', 'Nuclear Generation', 'Residual Demand', 'OCGT', 'Wind', 'PV', 'CSP', 'Renewables']
    assert august[required].notna().all().all()
    monthly = data.resample('MS').mean()
    OUT.mkdir(parents=True, exist_ok=True)

    fig, ax = figure('Availability eased, but this was the best August since 2018',
                      'Derived monthly EAF  |  August 2026: 71.0%, down 4.6 percentage points from July', '% of installed Eskom capacity')
    for year, color, width in [(2023, '#c7ceca', 1.5), (2024, '#91a399', 1.5), (2025, BLUE, 2), (2026, GREEN, 3)]:
        series = monthly.loc[str(year), 'EAF']
        ax.plot(series.index.month, series, color=color, linewidth=width, label=str(year), marker='o', markersize=3)
    ax.set_xticks(range(1,13), ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'])
    ax.set_ylim(45,85)
    ax.annotate('71.0%', (8, monthly.loc['2026-08-01','EAF']), xytext=(10,-3), textcoords='offset points', color=GREEN, weight='bold')
    ax.legend(frameon=False, ncol=4, loc='lower right')
    save(fig, 'img-eaf.png')

    recent = monthly.loc['2025':]
    fig, ax = figure('Planned maintenance explains the increase in total outages',
                      'Monthly average losses  |  July → August: planned +2.60 GW; unplanned −0.51 GW', 'GW of unavailable capacity')
    x = np.arange(len(recent))
    bottom = np.zeros(len(x))
    for column, label, color in [('Total UCLF', 'Unplanned', RED), ('Total PCLF', 'Planned', GOLD), ('Total OCLF', 'Other', BLUE)]:
        values = recent[column].to_numpy()/1000
        ax.bar(x, values, bottom=bottom, width=.72, label=label, color=color)
        bottom += values
    ticks = list(range(0,len(x),2)) + [len(x)-1]
    ax.set_xticks(ticks, [recent.index[i].strftime('%b %y') for i in ticks], fontsize=9)
    ax.set_ylim(0,24)
    ax.legend(frameon=False, ncol=3, loc='upper right')
    ax.annotate('13.73', (x[-1],bottom[-1]), xytext=(0,6), textcoords='offset points', ha='center', weight='bold')
    save(fig, 'img-clf.png')

    fig, ax = figure('Nuclear output fell sharply at the end of August',
                      'Hourly reported nuclear generation  |  Monthly average: 523 MW, versus 652 MW in July', 'MW, as reported in the export')
    ax.plot(august.index, august['Nuclear Generation'], color=GREEN, linewidth=1.7)
    ax.axhline(0, color=GRAY, linewidth=1)
    ax.axvspan(pd.Timestamp('2026-08-27 01:00'), pd.Timestamp('2026-08-31 02:00'), color=RED, alpha=.14)
    ax.text(pd.Timestamp('2026-08-22'), 730, '98 consecutive negative readings\n27 Aug 01:00–31 Aug 02:00', fontsize=10, color='#a2464c')
    ax.set_ylim(-90,820)
    ax.set_xlim(pd.Timestamp('2026-08-01'), pd.Timestamp('2026-09-01'))
    ax.set_xticks(pd.to_datetime([f'2026-08-{day:02}' for day in [1,5,10,15,20,25,31]]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    save(fig, 'img-nuclear.png')

    history = monthly[monthly.index.month==8]
    fig, ax = figure('Grid demand reached another August low',
                      'Average residual demand in August  |  2026: 20,920 MW, down 6.6% year on year', 'Average residual demand, GW')
    ax.bar(history.index.year, history['Residual Demand']/1000,
           color=[GREEN if y==2026 else '#a9bbae' for y in history.index.year], width=.7)
    ax.set_xticks(history.index.year)
    ax.set_ylim(0,30)
    for year, value in zip(history.index.year, history['Residual Demand']/1000):
        ax.text(year, value+.4, f'{value:.1f}', ha='center', fontsize=10)
    save(fig, 'img-demand.png')

    fig, ax = figure('Diesel turbine peaks returned after a quiet July',
                      'Combined Eskom + IPP OCGT output  |  August peak: 2,647 MW at 19:00 on 3 August', 'MW')
    current = monthly.loc['2026']
    peak = data['OCGT'].resample('MS').max().loc['2026']
    x=np.arange(len(current))
    ax.bar(x, current['OCGT'], color=RED, label='Monthly average', width=.5)
    ax.plot(x, peak, color=GOLD, linewidth=2.5, marker='o', label='Hourly peak')
    ax.set_xticks(x, current.index.strftime('%b'))
    ax.set_ylim(0,3300)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f'{value:,.0f}'))
    ax.legend(frameon=False, loc='upper left')
    ax.annotate('2,647', (7, peak.iloc[-1]), xytext=(0,10), textcoords='offset points', ha='center', weight='bold')
    ax.annotate('152', (7,current['OCGT'].iloc[-1]), xytext=(0,6), textcoords='offset points', ha='center', color=RED)
    save(fig, 'img-ocgt.png')

    fig, ax = figure('Solar set August peaks; total renewable output was flat',
                      'Average August generation  |  Wind + PV + CSP + other renewables: 1,863 MW, down 0.9% year on year', 'Average generation, MW')
    hist=history.loc['2021':]
    x=np.arange(len(hist)); bottom=np.zeros(len(hist))
    for col,label,color in [('Wind','Wind',BLUE),('PV','PV',GOLD),('CSP','CSP',GREEN),('Other RE','Other','#a7b2ac')]:
        values=hist[col].to_numpy()
        ax.bar(x,values,bottom=bottom,color=color,label=label,width=.6)
        bottom+=values
    ax.set_xticks(x,hist.index.year)
    ax.set_ylim(0,2700)
    ax.legend(frameon=False,ncol=4,loc='upper left')
    for i,total in enumerate(bottom):ax.text(i,total+45,f'{total:,.0f}',ha='center',fontsize=10)
    save(fig, 'img-renewables.png')
    print(monthly.loc[['2025-08-01','2026-07-01','2026-08-01'],required].to_string())
    print(f'Wrote six charts to {OUT}')


if __name__ == '__main__':
    main()
