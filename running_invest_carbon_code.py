# Libby Kula
# 1/6/2024
# Purpose: Running InVEST Carbon model for the contiguous US
# Update: Using global_invest carbon pools csv 

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
import multiprocessing as mp
import hazelbean as hb
import rasterio
from rasterio.mask import mask
import re 
import shutil
import sys

import natcap.invest.carbon
import natcap.invest.utils

os.chdir('C:/Users/kibby/OneDrive/Desktop/Research/DOI/')

######## RUNNING INVEST CARBON MODEL, LOOPING THROUGH YEARS ##########
for year in ['2001', '2011', '2021']:   
    if year in ['2001', '2011']:
        nlcd_path = 'NLCD/nlcd_' + year + '_land_cover_l48_20210604/nlcd_' + year + '_wgs84.tif'
    else:
        nlcd_path = 'NLCD/nlcd_' + year + '_land_cover_l48_20230630/nlcd_' + year + '_wgs84.tif'
    
    if os.path.exists(re.sub(r'wgs84', r'nad83', nlcd_path)) == 0:
        nlcd_dataset = gdal.Open(nlcd_path) 
        gdal.Warp(re.sub(r'wgs84', r'nad83', nlcd_path), nlcd_dataset, dstSRS='EPSG:5070') 

    # Runnng the carbon InVEST model
    args = {
        'calc_sequestration': False,
        'carbon_pools_path': 'Carbon Pools/nlcd_carbon_biophysical_table.csv',
        'discount_rate': '',
        'do_redd': False,
        'do_valuation': False,
        'lulc_cur_path': re.sub(r'wgs84', r'nad83', nlcd_path),
        'lulc_cur_year': '',
        'lulc_fut_path': '',
        'lulc_fut_year': '',
        'lulc_redd_path': '',
        'price_per_metric_ton_of_c': '',
        'rate_change': '',
        'results_suffix': year,
        'workspace_dir': 'InVEST Results/carbon workspace/3_15_2024/' + year,
    }
    natcap.invest.carbon.execute(args)

########## Resizing #######
def compress_tifs(path):
    #Open the input raster
    input_raster_path = path
    output_raster_path = re.sub('.tif', '_compress.tif', path)

    # Open the dataset
    src_ds = gdal.Open(input_raster_path)

    # Define the output options, including compression
    creation_options = ['COMPRESS=LZW', 'TILED=YES', 'BIGTIFF=IF_SAFER']

    # Use gdal.Translate to apply the compression
    gdal.Translate(output_raster_path, src_ds, creationOptions=creation_options)

    # Close the dataset
    src_ds = None
    
    os.remove(input_raster_path)

# carbon_path1= 'Code/carbon workspace/3_15_2024/tot_c_cur_' + '2011' + '.tif'
# carbon_path2= 'Code/carbon workspace/3_15_2024/tot_c_cur_' + '2021' + '.tif'

# pygeo.align_and_resize_raster_stack([carbon_path1, carbon_path2],
#                                     [re.sub('.tif', '_30m.tif', carbon_path1), re.sub('.tif', '_30m.tif', carbon_path2)],
#                                     resample_method_list=['bilinear', 'bilinear'],
#                                     target_pixel_size= (30, -30),
#                                     bounding_box_mode = 'intersection')

# compress_tifs(re.sub('.tif', '_30m.tif', carbon_path1))
# compress_tifs(re.sub('.tif', '_30m.tif', carbon_path2))
