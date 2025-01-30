# Libby Kula
# DOI NCA
# Equity/InVEST proposal 
# 11/7/2024
# Purpose: Fixing cooling results using cooling degree days 

import logging
import numpy as np
import os
import pygeoprocessing as pygeo
import pandas as pd
import geopandas as gpd
from osgeo import gdal
from osgeo import gdalconst
from osgeo import gdalnumeric
from osgeo import ogr
from matplotlib import pyplot as plt
import multiprocessing as mp
import hazelbean as hb
import ineqpy
import rasterio
from rasterio.mask import mask
import re 
import requests
import sys
import time
from scipy.stats import ttest_ind
from scipy.stats import mannwhitneyu
from shapely.geometry import Polygon, LineString
from shapely.ops import split
from shapely import LineString
import statsmodels.api as sm
from itertools import combinations

os.chdir("C:/Users/kibby/OneDrive/Desktop/Research/DOI/")

def monthly_temp_degC_to_cdd(temp_series):
    # Convert average temperature from Celsius to Fahrenheit
    avg_temp_c = temp_series
    avg_temp_f = avg_temp_c * 9/5 + 32

    # Define the threshold temperature in Fahrenheit
    threshold_temp_degf = 70

    # Create an empty Series for the results
    cdd_m = pd.Series(index=avg_temp_c.index)

    # Apply the condition and calculate cdd_m
    above_threshold = avg_temp_f >= threshold_temp_degf
    below_threshold = avg_temp_f < threshold_temp_degf

    cdd_m[above_threshold] = 29.58 * avg_temp_f[above_threshold] - 1905
    cdd_m[below_threshold] = 1.07 * (10**(-18)) * avg_temp_f[below_threshold]**10.96

    # Getting it back in Celsius 
    cdd_m = cdd_m*(5/9) 

    return cdd_m

temp_data = pd.read_csv("Data/Results/Metros/avg_temp_metros.csv") 
temp_data['cdd_m'] = monthly_temp_degC_to_cdd(temp_data['Average temp (degC)'])

# Add together the three months' CDD_m to get annual CDD 
annual_data = temp_data[['Metro', 'cdd_m']] 
annual_data = annual_data.groupby(['Metro']).sum().reset_index()
annual_data = annual_data.rename(columns={'cdd_m': 'cdd'})

metro_list = annual_data['Metro'].to_list()

energy_consump = {}
for c in metro_list:
    c_orig = c
    c = re.sub(r'\/', '-', c)
    metro_consump = pd.read_csv('Data/Energy Consumption Table/Metro tables/' + c + '.csv')
    kwh_m2_year = metro_consump['consumption'].iloc[0]
    energy_consump[c_orig] = kwh_m2_year

energy_df = pd.DataFrame.from_dict(energy_consump, orient='index', columns=['energy_consump'])
energy_df.index.name = 'Metro'
energy_df.reset_index(inplace=True)

energy_cdd_df = pd.merge(annual_data, energy_df,
                         how='inner', on='Metro')

# Performing the regression and fitting the model
result = sm.OLS(energy_cdd_df['energy_consump'], energy_cdd_df['cdd']).fit()

# Saving the coefficient as the cooling gradient m_c
mc = result.params[0]
print(mc)

### Fixing my energy savings valuation ### 

multistate_path = 'Code/cooling workspace/3_16_2024_fixed_multistate/'
multistate_metro_list = [
    foldername
    for foldername in os.listdir(multistate_path) 
]

singlestate_path = 'Code/cooling workspace/11_21_2023_metros/'
singlestate_metro_list = [
    foldername
    for foldername in os.listdir(singlestate_path) 
]

metro_list = multistate_metro_list + singlestate_metro_list

metro_list.sort()

uhi_data = pd.read_csv('Data/Results/uhi_4_29_2024_v03.csv')
consump_fixed_table = pd.read_csv('Data/Results/Metros/consumption_fixed.csv')
build_heights = pd.read_csv('Data/Energy Consumption Table/Continental_building_height/OutputData_CombinedModel/us/Metros/metros_build_height.csv')

# for c in metro_list:
def fix_cooling_fixed(c):
    print(c)
    if c == 'Louisville-Jefferson County, KY-IN':
        c_orig = 'Louisville/Jefferson County, KY-IN'
    else:
        c_orig = c
    
    c = re.sub(r'\/', '-', c)

    prev_energy_table = pd.read_csv('Data/Energy Consumption Table/Metro tables/' + c + '.csv')
    prev_consump = prev_energy_table['consumption'].iloc[0]

    filtered_df = build_heights[build_heights['metro'] == c_orig]
    avg_floors = filtered_df['avg_build_floors'].iloc[0] # need to include to get from consumption by floor area to footprint area

    metro_consump = pd.read_csv('Data/Energy Consumption Table/Metro tables/' + c + '.csv')
    building_cost = metro_consump['cost'].iloc[0]
    
    for month in ['06', '07', '08']:
        build_temp_df = pd.read_csv('Data/Results/Metros/building_avg_temps/build_temp_w_nat_' + c + '_' + month + '.csv')
        for year in ['2001', '2011', '2021']:
            results_dict = {}
            building_path = "Code/cooling workspace/11_21_2023_metros/" + c + "/buildings_with_stats_" + c + "_" + year + "_" + month + "_fixed.shp"
            hm_path = 'Code/cooling workspace/11_21_2023_metros/' + c + '/hm_' + c + '_' + year + '_' + month + '.tif'
             
            buildings_gdf = gpd.read_file(building_path)
            buildings_gdf = buildings_gdf.to_crs('EPSG:5070')
            building_area_m2 = buildings_gdf.area 

            uhi_max = uhi_data['uhi'][(uhi_data['metro'] == c_orig) & (uhi_data['month'] == int(month))].iloc[0]

            gdal.Warp(re.sub(r'\.(.*?)$', r"_clipped_{}.\1".format(re.sub(r'\/', '-', c)), hm_path), 
                hm_path, cutlineDSName='Data/Polygon_vectors/Administrative_Boundaries of_National Park_System_Units/Chattahoochee River National Recreation Area_700m_buffer.gpkg', cropToCutline=True)
            gdal.Warp(re.sub(r'.tif', r"_{}_clipped_wgs84.tif".format(c), hm_path), 
                      re.sub(r'\.(.*?)$', r"_clipped_{}.\1".format(re.sub(r'\/', '-', c)), hm_path), dstSRS='EPSG:4326')
            
            buildings_gdf_wgs84 = buildings_gdf.to_crs('EPSG:4326')
            buildings_gdf_wgs84.to_file(re.sub('.shp', '_Aug30_wgs84.gpkg', building_path))
            
            t = time.localtime()
            current_time = time.strftime("%H:%M:%S", t)
            print('Before zonal stats: ', current_time)
            hm_stats = pygeo.zonal_statistics(base_raster_path_band = (re.sub(r'\.(.*?)$', r"_clipped_{}.\1".format(re.sub(r'\/', '-', c)), hm_path), 1),
                                                        aggregate_vector_path = re.sub('.shp', '_Aug30_wgs84.gpkg', building_path),
                                                        ignore_nodata = True)
            t = time.localtime()
            current_time = time.strftime("%H:%M:%S", t)
            print('After zonal stats: ', current_time)

            buildings_gdf['avg_cc'] = 0
            for i in range(1, len(buildings_gdf) + 1):
                if hm_stats[i]['count'] >0: 
                    buildings_gdf['avg_cc'][i] = hm_stats[i]['sum']/hm_stats[i]['count']

            t = time.localtime()
            current_time = time.strftime("%H:%M:%S", t)
            print('After avg cc: ', current_time)

            build_temp_w_nat = build_temp_df['build_temp_w_nat']
            build_deg_cooling = uhi_max*buildings_gdf['avg_cc']  
            build_temp_wo_nat = build_temp_w_nat + build_deg_cooling

            build_consump_saved = (monthly_temp_degC_to_cdd(build_temp_wo_nat) - monthly_temp_degC_to_cdd(build_temp_w_nat))*mc 
            buildings_gdf['sav_upd'] = build_consump_saved*building_area_m2*building_cost*avg_floors
            
            results_dict['metro'] = c
            results_dict['year'] = year
            results_dict['month'] = month
            results_dict['sav_upd_sum'] = buildings_gdf['sav_upd'].sum() # Updated/fixed savings results

            results_dict['energy_sav_sum'] = buildings_gdf['energy_sav'].sum() # Orginal model savings resutls for comparison

            row_df = pd.DataFrame.from_dict(results_dict, orient='index') 
            row_df.to_csv('Data/Results/Wallpapered/cooling contrib/' + c + '_' + year + '_' + month + '.csv')

# ### PARALLEL PROCESSING ####
# if __name__ == '__main__':
#     mp.freeze_support() # This is recommended on Windows
#     # Step 1: Init multiprocessing.Pool()
#     pool = mp.Pool(mp.cpu_count() -5)

#     # Step 2: `pool.map` the `prep_and_run_cooling()` function
#     pool.map(fix_cooling_fixed, [c for c in metro_list])

#     # Step 3: Don't forget to close
#     pool.close()    
#     pool.join()

