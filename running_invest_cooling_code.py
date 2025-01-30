# Libby Kula
# Urban InVEST Urban Cooling ecosystem service model
# 6/28/2024
# Purpose: Prepare inputs and run Urban InVEST Urban Cooling model for all 380 U.S. metropolitan areas

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
import natcap.invest.urban_cooling_model
import natcap.invest.utils
import fiona

fiona.Env(SHAPE_RESTORE_SHX='YES')

os.chdir("C:/Users/kibby/OneDrive/Desktop/Research/DOI/Data")

#### Parallel processing setup ####
# print("Number of processors: ", mp.cpu_count())

#### Hazelbean just to check spatial projections/bb ####
nlcd_wgs_unit = hb.get_linear_unit('NLCD/nlcd_2021_land_cover_l48_20230630/nlcd_2021_wgs84.tif')
wkt_wgs84 = hb.get_wkt_from_epsg_code(4326)

# Valid metros list 
vector_gdf = gpd.read_file("Polygon_vectors/humidity_included/Metros/metros_hum_inc.gpkg")
metro_list = vector_gdf['NAME_right'].unique().tolist()
metro_list.sort()

# Done list 
results_path = '../InVEST Results/cooling workspace/'
done_list = [
    foldername
    for foldername in os.listdir(results_path) 
]

# Rural reference temperature from nearest neighbor matching
rural_gdf = gpd.read_file("Polygon_vectors/rural_pop.shp")
neighbors_gdf = gpd.read_file("Polygon_vectors/metros_nearest_neighbors_reftemp.shp")


######## USEFUL FUNCTIONS ##############################################
def clip_to_metro(ras, c):
    raster_dataset = gdal.Open(ras)
    if os.path.exists(re.sub(r'\.(.*?)$', r"_clipped_{}.\1".format(c), ras)) == 0:
        gdal.Warp(re.sub(r'\.(.*?)$', r"_clipped_{}.\1".format(c), ras), 
                raster_dataset, cutlineDSName="Polygon_vectors/Metros/" + c + ".gpkg", cropToCutline=True)
    if os.path.exists(re.sub(r'\.(.*?)$', r"_clipped_{}_nad83.\1".format(c), ras)) == 0:
        gdal.Warp(re.sub(r'\.(.*?)$', r"_clipped_{}_nad83.\1".format(c), ras), 
            re.sub(r'\.(.*?)$', r"_clipped_{}.\1".format(c), ras), dstSRS='EPSG:5070')

def calc_uhi(c_orig, month):
    c = re.sub(r'\/', '-', c_orig)  
    raster_paths = ['Evapotranspiration/Global-ET0_monthly_v3/Global-ET0_v3_monthly/et0_V3_' + month + '_aligned_wgs84.tif', 
                        'Reference Air Temperature/PRISM_tmean_30yr_normal_800mM4_' + month + '_bil/PRISM_tmean_30yr_normal_800mM4_' + month + '_bil_wgs84.bil'] 
    neighbors_gdf_c = neighbors_gdf[neighbors_gdf['NAME'] == c_orig]
    rural_ref_name = neighbors_gdf_c["CITYSTAT_1"].iloc[0]
    rural_ref = rural_gdf[rural_gdf['citystate'] == rural_ref_name]
    rural_ref = rural_ref.to_crs('EPSG:4326')
        
    # adding buffers to rural_ref for all cities to take care of those with small areas 
    buffers = rural_ref.geometry.buffer(distance = 15*nlcd_wgs_unit)
    rural_ref_buffer = rural_ref
    rural_ref_buffer['geometry'] = buffers
    rural_ref_buffer.to_file("Polygon_vectors/rural_ref" + c + ".shp") 
    rural_ref_name = rural_ref_buffer["citystate"].iloc[0]
    rural_ref.to_file("Polygon_vectors/Metros/rural_refs/rural_ref" + c + ".shp") 
    rural_ref_name = rural_ref["citystate"].iloc[0]
    
    temp_mean = gdal.Open(raster_paths[1])
    gdal.Warp(re.sub(r'\.(.*?)$', r"_rural_ref_{}.\1".format(c), raster_paths[1]), 
                        temp_mean, cutlineDSName="Polygon_vectors/Metros/rural_refs/rural_ref" + c + ".shp", cropToCutline=True) 
                
    rural_ref_stats = pygeo.zonal_statistics(base_raster_path_band = (re.sub(r'\.(.*?)$', r"_rural_ref_{}.\1".format(c), raster_paths[1]), 1),
                                                        aggregate_vector_path = "Polygon_vectors/Metros/rural_refs/rural_ref" + c + ".shp",
                                                        ignore_nodata = True)
    rural_ref_temp = rural_ref_stats[0]['sum']/rural_ref_stats[0]['count']

    rural_ref_path = re.sub(r'\.(.*?)$', r"_rural_ref_{}.\1".format(c), raster_paths[1])

    clip_to_metro(raster_paths[1], c)

    urban_ref_stats = pygeo.zonal_statistics(base_raster_path_band = (re.sub(r'\.(.*?)$', r"_clipped_{}.\1".format(c), raster_paths[1]), 1),
                                                        aggregate_vector_path ="Polygon_vectors/Metros/" + c + ".shp", 
                                                        ignore_nodata = True)
    urban_max = urban_ref_stats[0]['max'] # using max of the averages here to get a baseline UHI change
    uhi = urban_max - rural_ref_temp
    return [uhi, rural_ref_temp]

def calc_uhi_buffered(c_orig, month, buffer_size):
    metro_gdf = vector_gdf[vector_gdf['NAME_right'] == c_orig] 
    metro_gdf = metro_gdf.to_crs('EPSG:5070')
    c = re.sub(r'\/', '-', c_orig)  
    raster_paths = ['Evapotranspiration/Global-ET0_monthly_v3/Global-ET0_v3_monthly/et0_V3_' + month + '_aligned_wgs84.tif', 
                        'Reference Air Temperature/PRISM_tmean_30yr_normal_800mM4_' + month + '_bil/PRISM_tmean_30yr_normal_800mM4_' + month + '_bil_wgs84.bil'] 
        
    # adding buffers to metro_gdf for all cities to take care of those with small reference areas 
    buffers = metro_gdf.geometry.buffer(distance = buffer_size)
    buffered_minus_original = buffers.difference(metro_gdf.geometry)
    ref_buffered = gpd.GeoDataFrame(geometry=buffered_minus_original, crs=metro_gdf.crs)
    ref_buffered = ref_buffered.to_crs('EPSG:4326')
    ref_buffered_path = 'Polygon_vectors/Metros/rural_refs/rural_ref_' + c + '_v02.shp'
    ref_buffered.to_file(ref_buffered_path)

    temp_mean = gdal.Open(raster_paths[1])
    gdal.Warp(re.sub(r'\.(.*?)$', r"_rural_ref_v02_{}.\1".format(c), raster_paths[1]), 
                        temp_mean, cutlineDSName=ref_buffered_path, cropToCutline=True) 
                
    rural_ref_stats = pygeo.zonal_statistics(base_raster_path_band = (re.sub(r'\.(.*?)$', r"_rural_ref_v02_{}.\1".format(c), raster_paths[1]), 1),
                                                        aggregate_vector_path = ref_buffered_path,
                                                        ignore_nodata = True)
    rural_ref_temp = rural_ref_stats[0]['sum']/rural_ref_stats[0]['count']

    clip_to_metro(raster_paths[1], c)

    urban_ref_stats = pygeo.zonal_statistics(base_raster_path_band = (re.sub(r'\.(.*?)$', r"_clipped_{}.\1".format(c), raster_paths[1]), 1),
                                                        aggregate_vector_path ="Polygon_vectors/Metros/" + c + ".shp", 
                                                        ignore_nodata = True)
    urban_max = urban_ref_stats[0]['max'] # using max of the averages here to get a baseline UHI change
    uhi = urban_max - rural_ref_temp
    return [uhi, rural_ref_temp]

######## RUNNING INVEST COOLING MODEL, LOOPING THROUGH CITIES ##########

def prep_and_run_cooling(c):
# for c in metro_list:
    c_orig = c
    metro_gdf = vector_gdf[vector_gdf['NAME_right'] == c] 
    metro_gdf = metro_gdf.to_crs('EPSG:4326')
    c = re.sub(r'\/', '-', c)  

    for index, row in metro_gdf.iterrows():
        geom = row['geometry']
        if not geom.is_valid:
            fixed_geom = geom.buffer(0)
            metro_gdf.at[index, 'geometry'] = fixed_geom
    if os.path.exists('Polygon_vectors/Metros/' + c + ".gpkg") == 0:
        metro_gdf.to_file('Polygon_vectors/Metros/' + c + ".gpkg")
    if os.path.exists('Polygon_vectors/Metros/' + c + ".shp") == 0:
        metro_gdf.to_file('Polygon_vectors/Metros/' + c + ".shp")
    
    year_list = ['2001', '2011', '2021']
        
    for year in year_list:    
        if year in ['2001', '2011']:
            nlcd_path = 'NLCD/nlcd_' + year + '_land_cover_l48_20210604/nlcd_' + year + '_wgs84.tif'
        else:
            nlcd_path = 'NLCD/nlcd_' + year + '_land_cover_l48_20230630/nlcd_' + year + '_wgs84.tif'
        
        nlcd_dataset = gdal.Open(nlcd_path) 

        gdal.Warp(re.sub(r'\.(.*?)$', r"_clipped_{}.\1".format(c), nlcd_path), 
                            nlcd_dataset, cutlineDSName='Polygon_vectors/Metros/' + c + ".gpkg", cropToCutline=True)
        gdal.Warp(re.sub(r'\.(.*?)$', r"_clipped_{}_nad83.\1".format(c), nlcd_path), 
                        re.sub(r'\.(.*?)$', r"_clipped_{}.\1".format(c), nlcd_path), dstSRS='EPSG:5070')
        
        month_list = ['06', '07', '08']

        # Looping through months 
        for month in month_list:
            print(f"Processing {year}-{month}")
            if month == '06':
                avg_humid = (metro_gdf['M_JUN'].iloc[0] + metro_gdf['A_JUN'].iloc[0])/2
            elif month == '07':
                avg_humid = (metro_gdf['M_JUL'].iloc[0] + metro_gdf['A_JUL'].iloc[0])/2
            else:
                avg_humid = (metro_gdf['M_AUG'].iloc[0] + metro_gdf['A_AUG'].iloc[0])/2
            
            raster_paths = ['Evapotranspiration/Global-ET0_monthly_v3/Global-ET0_v3_monthly/et0_V3_' + month + '_aligned_wgs84.tif', 
                            'Reference Air Temperature/PRISM_tmean_30yr_normal_800mM4_' + month + '_bil/PRISM_tmean_30yr_normal_800mM4_' + month + '_bil_wgs84.bil'] 

            # Masking input rasters to metro
            for ras in raster_paths:
                raster_dataset = gdal.Open(ras)
                gdal.Warp(re.sub(r'\.(.*?)$', r"_clipped_{}.\1".format(c), ras), 
                                raster_dataset, cutlineDSName="Polygon_vectors/Metros/" + c + ".gpkg", cropToCutline=True)
                gdal.Warp(re.sub(r'\.(.*?)$', r"_clipped_{}_nad83.\1".format(c), ras), 
                                re.sub(r'\.(.*?)$', r"_clipped_{}.\1".format(c), ras), dstSRS='EPSG:5070')

            # Getting rural reference temperature and UHIs            
            uhi_results = calc_uhi(c_orig, month) # Can replace with calc_uhi_buffered function if that is the rural reference temperature method you prefer
            uhi = uhi_results[0]
            rural_ref_temp = uhi_results[1]
            
            # Runnng the cooling Urban InVEST model
            args = {
                'aoi_vector_path': 'Polygon_vectors/Metros/' + c + '.gpkg',
                'avg_rel_humidity': str(avg_humid),
                'biophysical_table_path': 'Biophysical Tables/biophysical_cooling_v03.csv',
                'building_vector_path': 'Built Infrastructure/Microsoft/Metros/' + c + '.gpkg', 
                'cc_method': 'factors',
                'cc_weight_albedo': '',
                'cc_weight_eti': '',
                'cc_weight_shade': '',
                'do_energy_valuation': False,
                'do_productivity_valuation': False,
                'energy_consumption_table_path': 'Energy Consumption Table/Metro tables/' + c + '.csv',
                'green_area_cooling_distance': '50',
                'lulc_raster_path': re.sub(r'\.(.*?)$', r"_clipped_{}_nad83.\1".format(c), nlcd_path),
                'n_workers': '-1',
                'ref_eto_raster_path': re.sub(r'\.(.*?)$', r"_clipped_{}_nad83.\1".format(c), raster_paths[0]),
                'results_suffix': c + '_' + year + '_' + month,
                't_air_average_radius': '600',
                't_ref': str(rural_ref_temp),
                'uhi_max': str(uhi),
                'workspace_dir': '../InVEST Results/cooling workspace/' + c,
                }
            natcap.invest.urban_cooling_model.execute(args)

# ### PARALLEL PROCESSING ####
# if __name__ == '__main__':
#     mp.freeze_support() # This is recommended on Windows
#     # Step 1: Init multiprocessing.Pool()
#     pool = mp.Pool(mp.cpu_count() -4)

#     # Step 2: `pool.map` the `prep_and_run_cooling()` function
    # pool.map(prep_and_run_cooling, [c for c in metro_list])

#     # Step 3: Don't forget to close
#     pool.close()    
#     pool.join()
            