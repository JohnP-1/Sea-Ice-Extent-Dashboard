import pandas as pd
import dash
import plotly.express as px
import os.path as path
from os import listdir
import re, html
import os
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
import numpy as np
import sys

def find_data_directory_path():
    ''' Returns the data directory path'''
    return path.join(path.dirname(path.realpath(__file__)), 'data')

def download_data(region):
    ''' Downloads the data to the data directory from the National Snow and Ice Data Center'''
    archive_url = f'https://noaadata.apps.nsidc.org/NOAA/G02135/{region}/monthly/data/'
    r = requests.get(archive_url)
    data = BeautifulSoup(r.text, "html.parser")
    for l in tqdm(data.find_all("a")[1:], desc=f'Downloading data files of the {region} region'):
        r = requests.get(archive_url + strip_tags(l["href"]))
        with open(path.join(find_data_directory_path(), l["href"]), "wb") as f:
            f.write(r.content)

def strip_tags(html):
    ''' Strips HTML tags from a string'''

    return re.sub('<[^<]+?>', '', html)

def check_if_data_exists():
    ''' Checks if the data directory exists, if it doesn't it will download the data, returns true if data is downloaded,
    or the datafolder already exists. Note this will not check if the individual datafiles are actually there!'''

    if not path.exists(find_data_directory_path()):
        response = input("The data directory doesn't exist, do you want to download it? ([y]/n):")
        if response == '':
            response = 'y'
        if response == 'y':
            os.makedirs(find_data_directory_path())
            download_data(region='north')
            download_data(region='south')
            return True
        else:
            return False
    else: return True

data_exists = check_if_data_exists()   # Check if the data exists

if not data_exists:
    print("You neeed to download the data for the dashboard to work...")
    sys.exit()

# load in the data, this is temporal so will be sorted first by year and then month
data = [pd.read_csv(path.join(find_data_directory_path(), f)) for f in listdir(find_data_directory_path())]
data = pd.concat(data, axis=0).sort_values(['year', ' mo']).reset_index(drop=True).replace(-9999, pd.NA)
data['day'] = 1 #Insert a dummy day column to enable simple conversion of datetime
data = data.rename({' mo':'month'}, axis=1)
data['Date'] = pd.to_datetime(data[['year', 'month', 'day']])

# Rename the regions to something meaningful
data.loc[data[data[' region']=='      S'].index, ' region'] = 'Antarctica'
data.loc[data[data[' region']=='      N'].index, ' region'] = 'Arctic'

# Create the dashboard
app = dash.Dash()

# Create the dashboard layout
app.layout = dash.html.Div([
    dash.html.Div(dash.dcc.Graph(id='graph-content', style={'width': '90vh', 'height': '90vh'}),
                  style={'padding': 10, 'flex': 1}),

    dash.html.Div(children=[
        # Add a title
        dash.html.H1(
                children='Sea Ice Extent in the Arctic and Antarctic Regions',
                style={
                    'textAlign': 'center',
                }
            ),
        dash.html.Br(), dash.html.Br(), ## Adds some space

        # This adds some descriptive text to the dashboard
        dash.html.Label('The sea ice extent is the expanse of sea covered by ice at a greater than 15% concentration. '
                        'This simple dashboard makes it possible to observe the change in sea ice extent over time in '
                        'both the Arctic and Antarctic regions. Notice the strong cyclic nature driven by seasonal '
                        'temperature patterns. Interestingly the Arctic sea ice extent is reducing at roughly a rate '
                        'of 5.5% per year, while the Antarctic sea ice extent has stayed relatively stable!'),
        dash.html.Br(), dash.html.Br(), dash.html.Br(), ## Adds some space

        # This is the code to create the range slider allowing the user to select the timescale they wish to view
        dash.html.Label('Choose the years you would like to display:'),
        dash.dcc.RangeSlider(
            min=data['year'].min(),
            max=data['year'].max(),
            marks={i: str(i) for i in range(data['year'].min(), data['year'].max(), 10)},
            id='year-selection',
            value=[data['year'].min(), data['year'].max()]
        ),
        dash.html.Br(), dash.html.Br(), ## Adds some space

        # A radio button set allowing the user to select which region they would like to view
        dash.html.Label('Region:'),
        dash.dcc.RadioItems(data[' region'].unique(),
                      data[' region'].unique()[0],
                      id='region-selection'
        ),

        dash.html.Br(), dash.html.Br(), ## Adds some space

        # Allows the user to selct if a trend will be shown, this can either be No trend, a yearly average or a best
        # fit line
        dash.html.Label('Display Trend:'),
        dash.dcc.RadioItems(options=['None', 'Yearly', 'Linear'],
                            value='None',
                      id='trend-selection'
        ),

        dash.html.Br(), dash.html.Br(), ## Adds some space
    ], style={'padding': 10, 'flex': 1})
], style={'display': 'flex', 'flexDirection': 'row'})

# This is the callback that responds to any changes in the inputs described above and changes the plot to be shown.
@dash.callback(
    dash.Output('graph-content', 'figure'),
    dash.Input('region-selection', 'value'),
    dash.Input('year-selection', 'value'),
    dash.Input('trend-selection', 'value')
)
def update_graph(value_region, value_year, value_trend):
    # Filters the dataframe based on the input selection
    data_filt = data[(data[' region']==value_region) & (data['year'] >= value_year[0]) & (data['year'] <= value_year[1])]

    # Initially creates the plot
    fig = px.line(data_filt, x='Date', y=' extent', color=' region',
                  labels={'Date': 'Date', ' extent': 'Extent (Millions of square Kilometers)'})

    if value_trend == 'Yearly':
        # This adds the yearly average plot
        data_filt_agg = data_filt.groupby(pd.PeriodIndex(data_filt['Date'], freq="Y"))[' extent'].mean().reset_index()
        data_filt_agg['Date'] = data_filt_agg['Date'].dt.to_timestamp() + pd.DateOffset(months=6)
        fig.add_scatter(x=data_filt_agg['Date'], y=data_filt_agg[' extent'], mode='lines', name='Yearly Trend')
    elif value_trend == 'Linear':
        # This adds the linear trend to the plot
        data_filt.loc[:, ' extent'] = data_filt[' extent'].dropna(axis=0).astype(np.float64)
        fig = px.scatter(data_filt, x='Date', y=' extent', color=' region',
                      labels={'Date': 'Date', ' extent': 'Extent (Millions of square Kilometers)'},
                         trendline="ols", trendline_color_override="red").update_traces(mode="lines")
    elif 'None':
        # Allows for removing any trend lines added
        fig = px.line(data_filt, x='Date', y=' extent', color=' region',
                      labels={'Date': 'Date', ' extent': 'Extent (Millions of square Kilometers)'})

    fig.update_layout(
        font_size=16
    )
    return fig

if __name__ == '__main__':
    app.run(debug=False)