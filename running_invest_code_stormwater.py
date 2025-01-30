# Libby Kula
# 3/27/2024
# Purpose: Running the Urban InVEST Urban Stormwater Retention Model for U.S. cities > 50,000 populations

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
import matplotlib.pyplot as plt
import hazelbean as hb
import rasterio
from rasterio.mask import mask
import re 
import sys
import multiprocessing as mp
import shutil


import natcap.invest.urban_cooling_model
import natcap.invest.stormwater
import natcap.invest.urban_flood_risk_mitigation
import natcap.invest.utils

os.chdir('C:/Users/kibby/OneDrive/Desktop/Research/DOI/Data')

##### Polygon vector and list of cities ######
vector_path = 'Polygon_vectors/humidity_included/usa_cities_50k_pop_hum.shp'
vector_gdf = gpd.GeoDataFrame(gpd.read_file(vector_path))
vector_gdf = vector_gdf.to_crs('EPSG:4326')
vector_gdf = vector_gdf[(vector_gdf['STATE_2'] != '2') & (vector_gdf['STATE_2'] != '15')] # taking out Alaska and Hawaii 

cities_build_height = pd.read_csv('Energy Consumption Table/Continental_building_height/OutputData_CombinedModel/us/City/cities_build_height.csv')
citystates_list = cities_build_height['city'].to_list()
citystates_list.sort()

biophys_refs = pd.read_csv('Polygon_vectors/Ecoregions/biophys_references.csv')

######## RUNNING INVEST STORMWATER MODEL, LOOPING THROUGH CITIES ##########
cso_cities = pd.read_excel('Polygon_vectors/cso_cities_intersecting_metros.xlsx', 'cso_cities_intersecting_metros')
cso_cities_list = cso_cities['citystate'].to_list()

cities_path = 'Polygon_vectors/usa_cities_50k_pop_reproj_83/usa_cities_50k_pop.shp'
cities_gdf = gpd.read_file(cities_path)

# for c in citystates_list:
def run_storm_model(c):
    print(c)
    c_orig = c
    c = re.sub(r'\/', '-', c) # regex for replacing slashes in city names with dashes for paths to work
    
    city_path = 'Polygon_vectors/' + c + '.gpkg'
    if os.path.exists(city_path) == 0:
        city_gdf = cities_gdf[cities_gdf['citystate'] == c_orig]
        city_gdf.to_file(city_path)
    else:
        city_gdf = gpd.read_file(city_path) 

    soil_path = 'Soil Hydrologic Group/Raster/Hydrologic Soil Group DCD (30 meter raster)1_reclass.tif' 

    # Masking input rasters to city
    soil_dataset = gdal.Open(soil_path)        
    gdal.Warp(re.sub(r'\.(.*?)$', r'_clipped_{}.\1'.format(c), soil_path), 
                soil_dataset, cutlineDSName='Polygon_vectors/' + c + '.gpkg', cropToCutline=True)
    gdal.Warp(re.sub(r'\.(.*?)$', r'_clipped_{}_nad83.\1'.format(c), soil_path), 
                re.sub(r'\.(.*?)$', r'_clipped_{}.\1'.format(c), soil_path), dstSRS='EPSG:5070')
            
    # Looping through years 
    for year in ['2001', '2011', '2021']:        
        if year in ['2001', '2011']:
            nlcd_path = 'NLCD/nlcd_' + year + '_land_cover_l48_20210604/nlcd_' + year + '_wgs84.tif'
        else:
            nlcd_path = 'NLCD/nlcd_' + year + '_land_cover_l48_20230630/nlcd_' + year + '_wgs84.tif'

        precip_path = 'Precipitation/PRISM_ppt_30yr_normal_800mM4_annual_bil/PRISM_ppt_30yr_normal_800mM4_annual_bil.bil'

        raster_paths = [nlcd_path, precip_path]
        
        for ras in raster_paths:
            raster_dataset = gdal.Open(ras)    
            
            gdal.Warp(re.sub(r'\.(.*?)$', r'_clipped_{}.\1'.format(c), ras), 
                    raster_dataset, cutlineDSName='Polygon_vectors/' + c + '.gpkg', cropToCutline=True)
            gdal.Warp(re.sub(r'\.(.*?)$', r'_clipped_{}_nad83.\1'.format(c), ras), 
                re.sub(r'\.(.*?)$', r'_clipped_{}.\1'.format(c), ras), dstSRS='EPSG:5070')
                
        # Ecoregion-specific biophysical table reference city
        biophys_ref = biophys_refs['reference'][biophys_refs['city'] == c].iloc[0]

        # Running the stormwater Urban InVEST model 
        args = {
            'adjust_retention_ratios': False,
            'aggregate_areas_path': city_path,   
            'biophysical_table': 'Biophysical Tables/Ecoregion-specific/' + 'biophysical_storm_' + biophys_ref + '_v02.csv',
            'lulc_path': re.sub(r'\.(.*?)$', r'_clipped_{}_nad83.\1'.format(c), nlcd_path),
            'n_workers': '-1',
            'precipitation_path': re.sub(r'\.(.*?)$', r'_clipped_{}_nad83.\1'.format(c), precip_path),
            'replacement_cost': '2.58',
            'results_suffix': c + '_' + year,
            'retention_radius': '',
            'road_centerlines_path': '',
            'soil_group_path': re.sub(r'\.(.*?)$', r'_clipped_{}_nad83.\1'.format(c), soil_path),
            'workspace_dir': '../InVEST Results/stormwater workspace/normals_precip/' + c,
            }
        # if __name__ == '__main__':
        natcap.invest.stormwater.execute(args)
    

# # PARALLEL PROCESSING ####
# if __name__ == '__main__':
#     mp.freeze_support() # This is recommended on Windows
#     # Step 1: Init multiprocessing.Pool()
#     pool = mp.Pool(mp.cpu_count() -2)

#     # Step 2: `pool.map` the `run_storm_model()` function
#     pool.map(run_storm_model, [c for c in cso_cities_list])

#     # Step 3: Don't forget to close
#     pool.close()    
#     pool.join()

