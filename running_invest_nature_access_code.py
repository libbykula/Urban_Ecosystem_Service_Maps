# Libby Kula
# 03/13/2024
# Purpose: Preparing inputs and running the Urban InVEST Urban Nature Access model

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

import natcap.invest.urban_nature_access
import natcap.invest.utils

os.chdir("C:/Users/kibby/OneDrive/Desktop/Research/DOI/Data/")

#### Parallel processing setup ####
# print("Number of processors: ", mp.cpu_count())

# Valid metros list 
vector_path = 'Polygon_vectors/tl_2019_us_cbsa/metros_boundaries.shp'
vector = gpd.read_file(vector_path)
metros_list = vector['NAME'].to_list()
metros_list.sort()

######## RUNNING INVEST URBAN NATURE ACCESS MODEL, LOOPING THROUGH YEARS ##########
def prep_and_run_nature(c):
    c = re.sub(r'\/', '-', c) 
    print(c)    
    
    for year in ['2001', '2011', '2021']:
        if year in ['2001', '2011']:
            nlcd_path = 'NLCD/nlcd_' + year + '_land_cover_l48_20210604/nlcd_' + year + '_wgs84.tif'
        else:
            nlcd_path = 'NLCD/nlcd_' + year + '_land_cover_l48_20230630/nlcd_' + year + '_wgs84.tif'
        
        prev_year = str(int(year) - 1)
        population_path =  'Population/gpw-v4-population-count-rev11_' + prev_year + '_30_sec_tif/gpw_v4_population_count_rev11_' + prev_year + '_30_sec.tif'        
        pop_wgs_unit = hb.get_linear_unit(population_path)

        raster_list = [nlcd_path, population_path]

        polygons_path = 'Census/Tract/Clipped/Metros/' + prev_year + '/' + c + '_valid_v02.gpkg'

        for ras in raster_list:
            if os.path.exists(re.sub(r'\.(.*?)$', r"_clipped_{}.\1".format(c), ras)) == 0:
                raster_dataset = gdal.Open(ras)
                gdal.Warp(re.sub(r'\.(.*?)$', r"_clipped_{}.\1".format(c), ras), 
                            raster_dataset, cutlineDSName="Polygon_vectors/Metros/" + c + ".gpkg", cropToCutline=True)

        # Open your raster file in read-write mode
        dataset = gdal.Open(re.sub(r'\.(.*?)$', r"_clipped_{}.\1".format(c), population_path), gdal.GA_Update)

        # Get the first band from the dataset
        band = dataset.GetRasterBand(1)

        # Read the raster data as an array
        array = band.ReadAsArray()

        # Change 0 values to 0.0000013641202
        array[array == 0] = 0.0000013641202 # Changing 0's to the smallest value to avoid breaking the Urban InVEST Urban Nature Access Model (it computes population share, undefined at pop = 0)

        # Write the modified array back to the raster
        band.WriteArray(array)

        # Close the dataset to flush changes
        dataset = None

        gdal.Warp(re.sub(r'\.(.*?)$', r"_clipped_nad83_{}.\1".format(c), population_path), 
                      re.sub(r'\.(.*?)$', r"_clipped_{}.\1".format(c), population_path), dstSRS='EPSG:5070', dstNodata=0) 
        gdal.Warp(re.sub(r'\.(.*?)$', r"_clipped_nad83_{}.\1".format(c), nlcd_path), 
                            re.sub(r'\.(.*?)$', r"_clipped_{}.\1".format(c), nlcd_path), dstSRS='EPSG:5070') 
                    
        # Runnng the nature access Urban InVEST model
        args = {
            'workspace_dir': 'InVEST Results/nature access workspace/' + c,
            'results_suffix': c + '_' + year,
            'n_workers': '-1',
            'lulc_raster_path': re.sub(r'\.(.*?)$', r"_clipped_nad83_{}.\1".format(c), nlcd_path),
            'lulc_attribute_table': 'LULC Attribute Table/lulc_attr_table.csv',
            'population_raster_path': re.sub(r'\.(.*?)$', r"_clipped_nad83_{}.\1".format(c), population_path),
            'admin_boundaries_vector_path': polygons_path,
            'urban_nature_demand': '50', # Russo & Cirella (2018) say the WHO recommend min of 9 m2, ideal of 50 m2
            'decay_function': 'gaussian', # dichotomy treats all pixels as equally accessible, the other options: exponential, Gaussian and density weight closer nature higher for accessibility
            'search_radius_mode': 'uniform radius',
            'search_radius': '1400' # needed for uniform search radius mode, taken from Brussels study (1400) 
        }
        
        # if __name__ == '__main__':
        natcap.invest.urban_nature_access.execute(args)
        
# # # #### PARALLEL PROCESSING ####
# if __name__ == '__main__':
#     mp.freeze_support() # This is recommended on Windows
#     # Step 1: Init multiprocessing.Pool()
#     pool = mp.Pool(mp.cpu_count() -2)

#     # Step 2: `pool.map` the `prep_and_run_nature()` function
#     pool.map(prep_and_run_nature, [c for c in metro_list])

#     # Step 3: Don't forget to close
#     pool.close()    
#     pool.join()

