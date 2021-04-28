# -*- coding: utf-8 -*-
"""
@author: Peter Betlem
@institution: University Centre in Svalbard, Svalbard
@year: 2020

The following classes are inspired by the UC Davis work, which in full
is documented here: https://github.com/ucdavis/metashape.
"""

from pathlib import Path
import datetime
import glob
import re
import logging
from logging.config import dictConfig
import yaml
import pandas as pd
from shutil import copyfile
import Metashape
import requests
from packaging import version



from .read_yaml import read_yaml
from .ImageMarkers import marker_detection, real_world_positions


import pkg_resources
import distutils.dist
import io

am = pkg_resources.get_distribution('automated_metashape')
metadata_str = am.get_metadata(am.PKG_INFO)
metadata_obj = distutils.dist.DistributionMetadata()
metadata_obj.read_pkg_file(io.StringIO(metadata_str))

__version__ = metadata_obj.version
__author__ = metadata_obj.author
__author_email__ = metadata_obj.author_email
__repository__ = metadata_obj.url

class AutomatedProcessing:

    # def _about(self):
        # self.__version__ = "2020-dec-02"
        # self.__author__ = "Peter Betlem"
        # self.__institution__ = "The University Centre in Svalbard"
        # self.__license__ = "BSD 3-Clause License"
        # self.__copyright__ = "(c) 2020, Peter Betlem"
        
    def __init__(self, config_file, logger=logging.getLogger(__name__)):
        self.__version__ = pkg_resources.get_distribution('automated_metashape').version
        self._check_metashape_activated() # do this before doing anything else...
        self._check_automated_metashape_update_available()
        
        self.logger = logger
        
        self.cfg = read_yaml(config_file)
        self.config_file = config_file
        
        self.run_name = self.cfg["run_name"]
        self.run_id = "_".join([self.run_name,stamp_time()])
        self.project_file = Path(
            self.cfg["project_path"], 
            '.'.join([self.run_id, 'psx']) 
            )
        
        self._init_filesystem()
        self._init_logging()
        self._init_metashape_document() 
        
        if "networkProcessing" in self.cfg and self.cfg["networkProcessing"]["enabled"]:
            self._init_network_processing()
            self.network = True
            self.logger.info('Network mode activated.')
            self._return_parameters(stage="networkProcessing") 
        else:
            self.network = False
            
    def _check_automated_metashape_update_available(self):
        
        latest = requests.get("https://api.github.com/repos/PeterBetlem/automated_metashape/releases/latest")
        internal = version.parse(self.__version__)
        try:
            external = version.parse(response.json()["tag_name"])
            if internal < external:
                print(f"automated_metashape update available (local version: {internal}; repo version: {external}). " + \
                      "Please update from https://github.com/PeterBetlem/automated_metashape/releases. " +\
                     "Make sure to also check for changes in the accepted yml parameters...!")
        except:
            print("Unable to verify remote version. Please try again.")
            pass        
        
    def _check_metashape_activated(self):
        if not Metashape.license.valid:
           raise FileNotFoundError(
                f"Metashape license failed to validate: {Metashape.license.valid}. " +\
                    f"Either run Metashape.license.activate('license_key_string') " +\
                        f"in which license_key_string is the license key used for " +\
                            f"activating Metashape. " +\
                f"Alternatively (RECOMMENDED), create a system-wide environment path " +\
                    f"named agisoft_LICENSE and points it to the " +\
                        f"Metashape license file in the Agisoft Metashape directory.")

    def _init_filesystem(self):
        
        self._check_environment()
        
        if not self.cfg["project_path"].exists():
            self.cfg["project_path"].mkdir(parents=True)
        if not self.cfg["project_path"].exists():
            self.cfg["project_path"].mkdir(parents=True)
        

    def _init_logging(self):
        # TODO: add configuration to the YML file
        if "enable_overwrite" in self.cfg and self.cfg["enable_overwrite"] and \
                self.cfg["load_project_path"] and self.cfg["load_project_path"].with_suffix('.log').is_file():
            log_file_name = self.cfg["load_project_path"].resolve().with_suffix('.log')
        else:
            log_file_name = Path(self.cfg["project_path"],self.run_id+'.log')
            
        log_dict = {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'standard': {
                    'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
                },
            },
            'handlers': {
                'default': {
                    'level': 'INFO',
                    'formatter': 'standard',
                    'class': 'logging.StreamHandler',
                },
                'file_handler': {
                    'level': 'INFO',
                    'filename': log_file_name,
                    'class': 'logging.FileHandler',
                    'formatter': 'standard'
                }
            },
            'loggers': {
                '': {
                    'handlers': ['file_handler','default'],
                    'level': 'INFO',
                    'propagate': True
                },
            }
        }
    
        dictConfig(log_dict)
        
        if "enable_overwrite" in self.cfg and self.cfg["enable_overwrite"]:
            if self.cfg["load_project_path"] and self.cfg["load_project_path"].with_suffix('.log').is_file():
                self.logger.info('--------------')
                self.logger.info('Continued run initiated.')
            else:
                self.logger.info('--------------')
                self.logger.info('Fresh run initiated.')
            
            
        elif self.cfg["load_project_path"] and self.cfg["load_project_path"].with_suffix('.log').is_file():
            copyfile(self.cfg["load_project_path"].with_suffix('.log'),
                  Path(self.cfg["project_path"],self.run_id+'.log')
                )
            self.logger.info('--------------')
            self.logger.info('Continued run initiated.')
            
        elif self.cfg["load_project_path"] and not self.cfg["load_project_path"].with_suffix('.log').is_file():
            self.logger.info('--------------')
            self.logger.info('Unable to load original processing log. ' + \
                            'Treating as fresh run. ' + \
                            'Fresh run initiated.')
            
        else:
            self.logger.info('--------------')
            self.logger.info('Fresh run initiated.')
    
        self.logger.info(f'Runtime id: {self.run_id}')
        self.logger.info('--------------')

        self.logger.info(f'Agisoft Metashape Professional Version: {Metashape.app.version}.')
        self.logger.info(f'Automated metashape package version: {self.__version__}.\n')
        
    def _return_parameters(self,stage=None,log=None):
        with open(self.config_file) as file:
            config_full = yaml.load(file, Loader=yaml.SafeLoader)
        
        if not stage:
            config_dump = {k: v for k, v in config_full.items() if not isinstance(config_full[k],dict)}
            stage = "startup"
        else:
            config_dump = {k: v for k, v in config_full.items() if k == stage}
        
        parameters = f'\n\n### Start of input file configuration for {stage}-stage ###\n'+\
                         yaml.dump(config_dump, default_flow_style=False)+\
                         f'### End of input file configuration for {stage}-stage ###\n'
        if log:
            self.logger.info(parameters)
        else:
            return parameters
        
    def _terminate_logging(self):
        self.logger.info('--------------')
        self.logger.info('Run completed.')
        self.logger.info('--------------\n')
        
    def _check_environment(self):
        if "onedrive" in str(self.cfg["load_project_path"]).lower():
            self.logger.error("Detected OneDrive folder for project - background fileupdating causes instability. Terminating...")
            raise
        
    def _init_metashape_document(self):
        self.doc = Metashape.Document()
        self.doc.read_only = False
        
        if self.cfg["load_project_path"]:
            self.doc.open(str(self.cfg["load_project_path"].resolve().with_suffix('.psx').as_posix()))
            self.logger.info(f'Loaded existing project {self.cfg["load_project_path"]}')
            
            if "enable_overwrite" in self.cfg and self.cfg["enable_overwrite"]:
                self.logger.warning("Overwriting original Metashape project enabled. " + \
                                    "Cancel run and disable self.cfg['enable_overwrite'] if unwanted behaviour!")
                self.project_file = self.cfg["load_project_path"].resolve().with_suffix('.psx')
        
        else:
            # Initialize a chunk, set its CRS as specified
            self.logger.info(f'Creating new project...')
            self.chunk = self.doc.addChunk()
            self.chunk.crs = Metashape.CoordinateSystem(self.cfg["project_crs"])
        
        # Save doc doc as new project (even if we opened an existing project, save as a separate one so the existing project remains accessible in its original state)
        self.doc.save(str(self.project_file.resolve().as_posix()))
        self.logger.info(f'Saved project as {str(self.project_file.resolve().as_posix())}'+self._return_parameters())
        
    def _init_network_processing(self):
        try:
            self.client = Metashape.NetworkClient()
            self.client.connect(self.cfg["networkProcessing"]["server_ip"])
            self.logger.info(f'Connected to network @ {self.cfg["networkProcessing"]["server_ip"]} running Metashape version {self.client.serverInfo()["version"]}.')
            self.network_root = self.cfg["networkProcessing"]["network_root"]
            self.task_batch = list()
        except (RuntimeError,NameError):
            raise
    
    def init_tasks(self):
        """
        Cycling through the entire predefined workflow. In this case the workflow
        is adjusted to that used at the University Centre in Svalbard.
        """
        
        # TODO: Add all other processing step options here as well
                
        if "addPhotos" in self.cfg and self.cfg["addPhotos"]["enabled"]:
            self.add_photos()
            
        if "analyzePhotos" in self.cfg and self.cfg["analyzePhotos"]["enabled"]:
            self.analyze_photos()
            
        if "detectGCPs" in self.cfg and self.cfg["detectGCPs"]["enabled"]:
            self.detect_gcps()
        
        if "addGCPs" in self.cfg and self.cfg["addGCPs"]["enabled"]:
            # TODO: find a nicer way to add subdivide_task to all dicts
            if self.cfg["subdivide_task"]: 
                self.cfg["addGCPs"]["subdivide_task"] = self.cfg["subdivide_task"]
            self.add_gcps() # call to original metashape_workflow_functions
            
        if "alignPhotos" in self.cfg and self.cfg["alignPhotos"]["enabled"]:
            # TODO: find a nicer way to add subdivide_task to all dicts
            if self.cfg["subdivide_task"]: 
                self.cfg["alignPhotos"]["subdivide_task"] = self.cfg["subdivide_task"]
            self.align_photos()
        
        if "optimizeCameras" in self.cfg and self.cfg["optimizeCameras"]["enabled"]:
            # TODO: find a nicer way to add subdivide_task to all dicts
            if self.cfg["subdivide_task"]: 
                self.cfg["optimizeCameras"]["subdivide_task"] = self.cfg["subdivide_task"]
            self.optimize_cameras()
            
        if "buildDepthMaps" in self.cfg and self.cfg["buildDepthMaps"]["enabled"]:
            # TODO: find a nicer way to add subdivide_task to all dicts
            if self.cfg["subdivide_task"]: 
                self.cfg["buildDepthMaps"]["subdivide_task"] = self.cfg["subdivide_task"]
            self.build_depth_maps()
        
        if "buildDenseCloud" in self.cfg and self.cfg["buildDenseCloud"]["enabled"]:
            # TODO: find a nicer way to add subdivide_task to all dicts
            if self.cfg["subdivide_task"]: 
                self.cfg["buildDenseCloud"]["subdivide_task"] = self.cfg["subdivide_task"]
            self.build_dense_cloud()
            
        if "filterDenseCloud" in self.cfg and self.cfg["filterDenseCloud"]["enabled"]:
            # TODO: find a nicer way to add subdivide_task to all dicts
            if self.cfg["subdivide_task"]: 
                self.cfg["filterDenseCloud"]["subdivide_task"] = self.cfg["subdivide_task"]
            self.filter_dense_cloud()
            
        if "buildMesh" in self.cfg and self.cfg["buildMesh"]["enabled"]:
            # TODO: find a nicer way to add subdivide_task to all dicts
            if self.cfg["subdivide_task"]: 
                self.cfg["buildMesh"]["subdivide_task"] = self.cfg["subdivide_task"]
            self.build_mesh()
            
        if "buildTexture" in self.cfg and self.cfg["buildTexture"]["enabled"]:
            # TODO: find a nicer way to add subdivide_task to all dicts
            if self.cfg["subdivide_task"]: 
                self.cfg["buildTexture"]["subdivide_task"] = self.cfg["subdivide_task"]
            self.build_texture()
            
        if "buildTiledModel" in self.cfg and self.cfg["buildTiledModel"]["enabled"]:
            # TODO: find a nicer way to add subdivide_task to all dicts
            if self.cfg["subdivide_task"]: 
                self.cfg["buildTiledModel"]["subdivide_task"] = self.cfg["subdivide_task"]
            self.build_tiled_model()
            
        if "buildDEM" in self.cfg and self.cfg["buildDEM"]["enabled"]:
            # TODO: find a nicer way to add subdivide_task to all dicts
            if self.cfg["subdivide_task"]: 
                self.cfg["buildDEM"]["subdivide_task"] = self.cfg["subdivide_task"]
            self.build_dem()
            
        self.export_report()
        
        if self.network:
            self._network_submit_batch()
        else:
            
            if "publishData" in self.cfg and self.cfg["publishData"]["enabled"]:
                self.publish_data()
        
        self._terminate_logging()
            
        del self.doc
            
    def _encode_task(self, task):
        """
        All tasks need to be encoded before submission to the Agisoft Metashape Network.
        This also includes passing along all the chunks that need processing.
        """
        
        encoded_task = Metashape.NetworkTask()
        encoded_task.name = task.name
        encoded_task.params = task.encode()
        for c in self.doc.chunks:
            encoded_task.frames.append((c.key,0))
        self.task_batch.append( encoded_task )
    
    def add_photos(self):
        
        # TODO: provide dictionary check to add_photos as per the other functions
        self.logger.info('Initiating add_photos step...')
        a = glob.iglob(str(Path(self.cfg["addPhotos"]["photo_path"],"**","*.*")))   #(([jJ][pP][gG])|([tT][iI][fF]))
        b = [path for path in a]
        photo_files = [x for x in b if (re.search("(.tif$)|(.jpg$)|(.TIF$)|(.JPG$)",x) and (not re.search("_mask.",x)))]
        
        
        ## Add them
        if self.cfg["addPhotos"]["enabled"] and self.cfg["addPhotos"]["multispectral"]:
            self.doc.chunk.addPhotos(photo_files, layout = Metashape.MultiplaneLayout)
            self.logger.info('Photos (multispectral) added to project.')
        else:
            self.doc.chunk.addPhotos(photo_files)
            self.logger.info('Photos added to project.')
            
        # add masks if present (preferably in same 1XXMEDIA folder, with suffix {image_name}_mask.img_ext)
        # TODO: Try function below
        if "masks" in self.cfg and self.cfg["masks"]["enabled"]:
            self.logger.warning('Masks are currently a semi-unsupported feature, use with caution...')
            
            mask_dict = [
            "path",
            "masking_mode",
            "mask_operation",
            "tolerance",
            "cameras",
            "mask_defocus",
            "fix_coverage",
            "keypoint_limit",
            "blur_threshold",
            "mask_tiepoints",
            ]
            
            mask_parameters = {}
            for key, value in self.cfg["masks"].items():
                if key in mask_dict:
                    mask_parameters[key] = value 
            
            mask_parameters["path"] = str(mask_parameters["path"].resolve())

            if not "cameras" in mask_parameters.keys():
                mask_count = 0
                for cam in self.doc.chunk.cameras:
                    mask_parameters["cameras"] = [cam]
                    try:
                        self.doc.chunk.generateMasks(
                            **mask_parameters
                            )
                        self.logger.debug(f'Applied mask to camera {cam}')
                        mask_count += 1
                    except:
                        pass
            else:
                mask_count = len(mask_parameters["cameras"])
                self.doc.chunk.generateMasks(
                            **mask_parameters
                            )
                
                
            self.logger.info(f'Masks have been applied to {mask_count} cameras.'+self._return_parameters(stage="masks"))
            
        ## Need to change the label on each camera so that it includes the containing folder
        for camera in self.doc.chunk.cameras:
            path = camera.photo.path
            path_parts = path.split("/")[-2:]
            newlabel = "/".join(path_parts)
            camera.label = newlabel
                       
        self.logger.info('Successfully relabeled cameras.')
            
        if self.cfg["addPhotos"]["enabled"] and self.cfg["addPhotos"]["remove_photo_location_metadata"]:
            for camera in self.doc.chunk.cameras:
                camera.reference.location = None
                camera.reference.rotation = None
                    
            self.logger.info('Removed camera reference coordinates for processing.')
            
    
        self.doc.save()
        self.logger.info('Finalised adding photos.'+self._return_parameters(stage="addPhotos"))

    
    def analyze_photos(self):
        analyzePhotos_dict = [
            "cameras",
            "filter_mask"
            ]
        analyzePhotos_parameters = []
        for key, value in self.cfg["analyzePhotos"].items():
            if key in analyzePhotos_dict:
                analyzePhotos_parameters[key] = value 
                
        if self.network:            
            self.logger.warning("Current version do not support photo selection based on photo quality - use standalone instead.")
            task = Metashape.Tasks.AnalyzePhotos()
            task.decode(analyzePhotos_parameters)
            self._encode_task(task)
            self.logger.info('Photo-analysis tasks added to network batch list.'+self._return_parameters(stage="analyzePhotos"))

        else:
            self.doc.chunk.analyzePhotos()
            self.logger.info('Photos analyzed.')
            
            if "quality_cutoff" in self.cfg["analyzePhotos"]:
                self.logger.info(f"Disabling all photos with quality values less than {self.cfg['analyzePhotos']['quality_cutoff']}.")
            else:
                self.cfg["analyzePhotos"]["quality_cutoff"] = 0.5
                self.logger.info(f"Disabling all photos with quality values less than 0.5 (recommended by Agisoft).")
            
            #if not "cameras" in analyzePhotos_parameters:
            #    analyzePhotos_parameters["cameras"] = self.doc.chunk.cameras
                
            for camera in self.doc.chunk.cameras:
                if float(camera.meta['Image/Quality']) < self.cfg["analyzePhotos"]["quality_cutoff"]:
                    camera.enabled = False
                    self.logger.debug(f'Disabled camera {camera}')
        
    def detect_gcps(self):
        '''
        Detects aruco markers and stores these in a csv file.
        Currently only aruco markers are supported; though may in future be expended
        to include Agisoft metashape markers.

        '''
        #real_world_positions(self.cfg, logger=self.logger)
        marker_detection(self.cfg, logger=self.logger)
        # TODO: port real_world_position class
        
    def add_gcps(self):
        '''
        Add GCPs (GCP coordinates and the locations of GCPs in individual photos.
        See the helper script (and the comments therein) for details on how to prepare the data needed by this function: R/prep_gcps.R
        Alternatively, see the https://github.com/PeterBetlem/image_processing repo for automated Python processing based on aruco markers and OpenCV
        '''
        
        self.chunk.marker_crs = Metashape.CoordinateSystem(self.cfg["addGCPs"]["gcp_crs"])

        self.logger.info('Adding ground control points.')
        ## Tag specific pixels in specific images where GCPs are located
        path = Path(self.cfg["addGCPs"]["photo_path"], "gcps", "prepared", "gcp_imagecoords_table.csv")
        marker_pixel_data = pd.read_csv(path,names=["marker","camera","x","y"])
    
        for index, row in marker_pixel_data.iterrows():
            camera = _get_camera(self.doc.chunk, row.camera)
            if not camera:
                print(row.camera + " camera not found in project")
                continue
            
            marker = _get_marker(self.doc.chunk, str(int(row.marker)))
            if not marker:
                marker = self.doc.chunk.addMarker()
                marker.label = str(int(row.marker))
                
            marker.projections[camera] = Metashape.Marker.Projection((float(row.x), float(row.y)), True)
    
        ## Assign real-world coordinates to each GCP
        path = Path(self.cfg["addGCPs"]["photo_path"], "gcps", "prepared", "gcp_table.csv")
        marker_coordinate_data = pd.read_csv(path,names=["marker","x","y","z"])
        
        for index, row in marker_coordinate_data.iterrows():
            marker = _get_marker(self.doc.chunk, str(int(row.marker)))
            if not marker:
                marker = self.doc.chunk.addMarker()
                marker.label = str(int(row.marker))
                
            marker.reference.location = (float(row.x), float(row.y), float(row.z))
            marker.reference.accuracy = (
                self.cfg["addGCPs"]["marker_location_accuracy"], 
                self.cfg["addGCPs"]["marker_location_accuracy"], 
                self.cfg["addGCPs"]["marker_location_accuracy"]
                )
    
        self.doc.chunk.marker_location_accuracy = (
            self.cfg["addGCPs"]["marker_location_accuracy"], 
            self.cfg["addGCPs"]["marker_location_accuracy"], 
            self.cfg["addGCPs"]["marker_location_accuracy"]
            )
        self.doc.chunk.marker_projection_accuracy = self.cfg["addGCPs"]["marker_projection_accuracy"]
        self.doc.chunk.updateTransform()

        self.doc.save()
        self.logger.info('Ground control points added.'+self._return_parameters(stage="addGCPs"))
   
        return True
        
    def align_photos(self):
        """
        Create a network processing task for photo alignment, including the match
        photos, align cameras, and optimize camera steps.
        """
        
        self.logger.info('Aligning photos...')
        matchPhotos_dict = [
            "downscale",
            "generic_preselection",
            "reference_preselection",
            "reference_preselection_mode",
            "filter_mask",
            "mask_tiepoints",
            "filter_stationary_points",
            "keypoint_limit",
            "tiepoint_limit",
            "keep_keypoints",
            "guided_matching",
            "reset_matches",
            "subdivide_task",
            "workitem_size_cameras",
            "workitem_size_pairs",
            "max_workgroup_size"
            ]
        alignCameras_dict = [
            "cameras",
            "min_image",
            "adaptive_fitting",
            "reset_alignment",
            "subdivide_task",
            ]
        
        match_parameters = {}
        for key, value in self.cfg["alignPhotos"].items():
            if key in matchPhotos_dict:
                match_parameters[key] = value 
        
        align_parameters = {}
        for key, value in self.cfg["alignPhotos"].items():
            if key in alignCameras_dict:
                align_parameters[key] = value 
            
        if self.network:            
            task = Metashape.Tasks.MatchPhotos()
            task.decode(match_parameters)
            self._encode_task(task)
            
            task = Metashape.Tasks.AlignCameras()
            task.decode(align_parameters)
            self._encode_task(task)
            
            if self.cfg["alignPhotos"]["enabled"] and self.cfg["alignPhotos"]["double_alignment"]:
                self.logger.warning("Re-alignment of non-aligned photos currently only supported in non-server mode...")
                
            self.logger.info('Photo-alignment tasks added to network batch list.'+self._return_parameters(stage="alignPhotos"))
                
        else:
            self.doc.chunk.matchPhotos(**match_parameters
                )
            self.logger.info('Photos matched.')
            self.doc.chunk.alignCameras(**align_parameters
                )
            self.doc.save()
            
            if self.cfg["alignPhotos"]["enabled"] and self.cfg["alignPhotos"]["double_alignment"]:
                align_parameters["reset_alignment"] = False
                aligned_photos = []   # empty list
                for camera in self.doc.chunk.cameras:
                    if camera.transform==None:
                        aligned_photos.append(camera)
               
                if len(aligned_photos)>0:
                    self.logger.info(f"Detected {len(aligned_photos)} cameras that failed alignment. Repeating alignment stage...")
                    self.doc.chunk.alignCameras(aligned_photos,**align_parameters)
                    self.doc.save()
                    aligned_photos = []   # empty list
                    for camera in self.doc.chunk.cameras:
                        if camera.transform==None:
                            aligned_photos.append(camera)
                    
                    self.logger.info(f"{len(aligned_photos)} non-aligned cameras remain.")
            self.logger.info('Cameras aligned.'+self._return_parameters(stage="alignPhotos"))
            
    def optimize_cameras(self):
        '''
        Optimize cameras
        '''   
        
        self.logger.info('Optimising camera alignment...')
        optimizeCameras_dict = [
            "adaptive_fitting",
            "fit_b1",
            "fit_b2",
            "fit_corrections",
            "adaptive_fitting",
            "fit_cx",
            "fit_cy",
            "fit_f",
            "fit_k1",
            "fit_k2",
            "fit_k3",
            "fit_k4",
            "fit_p1",
            "fit_p2",
            ]
        
        optimize_parameters = {}
        for key, value in self.cfg["optimizeCameras"].items():
            if key in optimizeCameras_dict:
                optimize_parameters[key] = value 
        
        # Disable camera locations as reference if specified in YML
        if "addGCPs" in self.cfg and self.cfg["addGCPs"]["enabled"] and self.cfg["addGCPs"]["optimize_w_gcps_only"]:
            self.logger.info('GCP-only optimisation enabled.')
            for camera in self.doc.chunk.cameras:
                camera.reference.enabled = False
        
        if self.network:
            
            task = Metashape.Tasks.OptimizeCameras()
            task.decode(optimize_parameters)
            self._encode_task(task)
            self.logger.info('Alignment-optimisation task added to network batch list.'+self._return_parameters(stage="optimizeCameras"))
            
        else:
            self.doc.chunk.optimizeCameras(
                **optimize_parameters
                )
            self.doc.save()
            self.logger.info('Optimised camera alignment.'+self._return_parameters(stage="optimizeCameras"))
            
    def build_depth_maps(self):
        
        # TODO: consider splitting into separated depth map and dense cloud steps
        
        self.logger.info('Generating depth maps...')
        buildDepth_dict = [
            "downscale",
            "filter_mode",
            "cameras",
            "reuse_depth",
            "max_neighbors",
            "subdivide_task",
            "workitem_size_cameras",
            "max_workgroup_size",
            ]
        
        depth_parameters = {}
        for key, value in self.cfg["buildDepthMaps"].items():
            if key in buildDepth_dict:
                depth_parameters[key] = value 
                   
        if self.network:
            task = Metashape.Tasks.BuildDepthMaps()
            task.decode(depth_parameters)
            self._encode_task(task)
            
            self.logger.info('Depth map task added to network batch list.')
            
        else:
            self.doc.chunk.buildDepthMaps(**depth_parameters)
            self.doc.save()
            self.logger.info('Depth maps built.')
                
        self._return_parameters(stage="buildDepthMaps",log=True)
        
               
    def build_dense_cloud(self):
        
        # TODO: consider splitting into separated depth map and dense cloud steps
        
        self.logger.info('Generating dense cloud...')

        buildDense_dict = [
            "point_colors",
            "point_confidence",
            "keep_depth",
            "max_neighbors",
            "subdivide_task",
            "workitem_size_cameras",
            "max_workgroup_size",
            ]
        
        dense_parameters = {}
        for key, value in self.cfg["buildDenseCloud"].items():
            if key in buildDense_dict:
                dense_parameters[key] = value 
        # Point confidence should always be calculated!
        dense_parameters["point_confidence"] = True    
        
        classify_dict = [
            "max_angle",
            "max_distance",
            "cell_size",
            "source",
            ]
        
        classify_parameters = {}
        for key, value in self.cfg["buildDenseCloud"].items():
            if key in classify_dict:
                classify_parameters[key] = value
                
        if self.network:       
            # build dense cloud
            task = Metashape.Tasks.BuildDenseCloud()
            task.decode(dense_parameters)
            self._encode_task(task)
            self.logger.info('Dense cloud tasks added to network batch list.')
            
            # Classify ground points
            if "classify" in self.cfg["buildDenseCloud"] and self.cfg["buildDenseCloud"]["classify"]:
        
                task = Metashape.Tasks.ClassifyGroundPoints()
                task.decode(classify_parameters)
                self._encode_task(task)
                self.logger.info('Ground point classification task added to network batch list.')
            
        else:
            self.doc.chunk.buildDenseCloud(**dense_parameters)
            self.doc.save()
            self.logger.info('Dense cloud built.')
                       
            if "classify" in self.cfg["buildDenseCloud"] and self.cfg["buildDenseCloud"]["classify"]:
                self.doc.chunk.dense_cloud.classifyGroundPoints(**classify_parameters)
                self.doc.save()
                self.logger.info('Ground points classified.')
                
        self._return_parameters(stage="buildDenseCloud",log=True)
            
    def filter_dense_cloud(self):
        '''
        Filters the dense cloud. 
        Currently only supports local processing.
        Currently only supports point_confidence filtering

        '''
        if self.cfg["filterDenseCloud"]["point_confidence_max"]:
            if self.network:
                self.logger.warning("Point confidence for dense clouds currently not supported through the networking interface. Parameters ignored. Try running it locally.")
            else:
                self.logger.info(f"Removing dense points with 0<confidence<{self.cfg['filterDenseCloud']['point_confidence_max']}")
                self.doc.chunk.dense_cloud.label = "Dense Cloud (unfiltered)"
                original_dc = self.doc.chunk.dense_cloud.copy()
                original_dc.label = f"Dense cloud ({self.cfg['filterDenseCloud']['point_confidence_max']}+ confidence)"
                self.doc.chunk.dense_cloud.setConfidenceFilter(0,self.cfg["filterDenseCloud"]["point_confidence_max"])
                self.doc.chunk.dense_cloud.removePoints(list(range(128))) #removes all "visible" points of the dense cloud
                self.doc.chunk.dense_cloud.resetFilters()
                
                self._return_parameters(stage="filterDenseCloud",log=True)
                self.doc.save()
        else:
            self.logger.warning("No filtering has occurred. Please configure 'filterDenseCloud'/'point_confidence_max' in the cfg file...")
            
    def build_mesh(self):
        '''
        Build mesh
        '''
        self.logger.info('Constructing a mesh...')
                
        buildMesh_dict = [
            "surface_type",
            "interpolation",
            "face_count",
            "face_count_custom",
            "source_data",
            "vertex_colors",
            "vertex_confidence",
            "metric_masks",
            "keep_depth",
            "trimming_radius",
            "subdivide_task",
            "workitem_size_cameras",
            "max_workgroup_size",
            ]
        
        mesh_parameters = {}
        for key, value in self.cfg["buildMesh"].items():
            if key in buildMesh_dict:
                mesh_parameters[key] = value 
                
        if self.network:
            
            # build depth maps only instead of also building the dense cloud ##?? what does
            task = Metashape.Tasks.BuildModel()
            task.decode(mesh_parameters)
            self._encode_task(task)
            self.logger.info('Mesh-building task added to network batch list.'+self._return_parameters(stage="buildMesh"))
                

        else:
            self.doc.chunk.buildModel(**mesh_parameters)
            self.doc.save()
            self.logger.info('Mesh has been constructed.'+self._return_parameters(stage="buildMesh"))
    
    def build_texture(self):
        '''
        Build UV maps and textures
        '''
        
        self.logger.info('Generating UV maps and textures...')
                
        buildUV_dict = [
            "mapping_mode",
            "page_count",
            "adaptive_resolution",
            "cameras"
            ]
        
        uv_parameters = {}
        for key, value in self.cfg["buildTexture"].items():
            if key in buildUV_dict:
                uv_parameters[key] = value 
                
        buildTexture_dict = [
            "blending_mode",
            "texture_size",
            "fill_holes",
            "ghosting_filter",
            "texture_type",
            "transfer_texture"
            ]
        
        texture_parameters = {}
        for key, value in self.cfg["buildTexture"].items():
            if key in buildTexture_dict:
                texture_parameters[key] = value 
                
        if self.network:
            
            # build UV maps
            task = Metashape.Tasks.BuildUV()
            task.decode(uv_parameters)
            self._encode_task(task)
            self.logger.info('UV mapping task added to network batch list.')
                
     
            # build textures, requires UV maps.
            task = Metashape.Tasks.BuildTexture()
            task.decode(texture_parameters)
            self._encode_task(task)
            self.logger.info('Texture generation task added to network batch list.'+self._return_parameters(stage="buildTexture"))
            
        else:
            self.doc.chunk.buildUV(**uv_parameters)
            self.logger.info('UV map constructed.')
            
            self.doc.chunk.buildTexture(**texture_parameters)
            self.doc.save()
            self.logger.info('Textures constructed.'+self._return_parameters(stage="buildTexture"))

    def build_tiled_model(self):
        '''
        Build tiled model
        '''
        
        self.logger.info('Generating tiles for tiled model...')
             
        buildTiles_dict = [
            "pixel_size",
            "tile_size",
            "source_data",
            "face_count",
            "ghosting_filter",
            "transfer_texture",
            "keep_depth",
            "classes",
            "subdivide_task",
            "workitem_size_cameras",
            "max_workgroup_size"
            ]
        
        tile_parameters = {}
        for key, value in self.cfg["buildTiledModel"].items():
            if key in buildTiles_dict:
                tile_parameters[key] = value 
                
        if self.network:
            # build tiled model
            task = Metashape.Tasks.BuildTiledModel()
            task.decode(tile_parameters)
            self._encode_task(task)
            self.logger.info('Model tiling task added to network batch list.'+self._return_parameters(stage="buildTiledModel"))
            
        else:            
            self.doc.chunk.buildTiledModel(**tile_parameters)
            self.doc.save()
            self.logger.info('Tiled model constructed.'+self._return_parameters(stage="buildTiledModel"))

    def build_dem(self):
        '''
        Build dem
        '''
        
        self.logger.info('Generating DEM...')
             
        buildDEM_dict = [
            "source_data",
            "interpolation",
            "projection",
            "region",
            "classes",
            "flip_x",
            "flip_y",
            "flip_z",
            "resolution",
            "subdivide_task",
            "workitem_size_tiles",
            "max_workgroup_size"
            ]
        
        dem_parameters = {}
        for key, value in self.cfg["buildDEM"].items():
            if key in buildDEM_dict:
                dem_parameters[key] = value 
                
        if self.network:
            # build dem
            task = Metashape.Tasks.BuildDem()
            task.decode(dem_parameters)
            self._encode_task(task)
            self.logger.info('DEM generation task added to network batch list.'+self._return_parameters(stage="buildDEM"))

            
        else:            
            self.doc.chunk.buildDem(**dem_parameters)
            self.doc.save()
            self.logger.info('DEM constructed.'+self._return_parameters(stage="buildDEM"))

    def publish_data(self):
        """
        Function to automatically upload data to a service

        """
        self.logger.info('Publishing data...')
             
        publish_dict = [
            "service",
            "source",
            "with_camera_track",
            "export_point_colors",
            "title",
            "description",
            "token",
            "is_draft",
            "is_private",
            "password"
            ]
        
        publish_parameters = {}
        for key, value in self.cfg["publishData"].items():
            if key in publish_dict:
                publish_parameters[key] = value 
        
        if self.network:
            self.logger.error("Metashape does currently not support publishing in network mode." + \
                              "Init stanalone processing instead...")
        else:
            
            self.doc.chunk.publishData(**publish_parameters)
            self.logger.info('Data published.'+self._return_parameters(stage="publishData"))
        
        
    def export_report(self):
        """
        Function to automatically create reports
        """
        output_file = str(self.project_file.resolve().with_suffix('.pdf').as_posix())
        if self.network:
            task = Metashape.Tasks.ExportReport()
            task.path = output_file
            self._encode_task(task)
            self.logger.info(f'A processing report will be exported to {output_file}.')
            
        else:
            try:
                self.doc.chunk.exportReport(path = output_file)
                self.logger.info(f'A processing report has been exported to {output_file}.')
            except:
                self.logger.warning("Failed to export report. Export report manually.")
            self.doc.save()
    
    def _network_submit_batch(self):
        """
        Script that submits the generated task list to the network.
        """
        self.doc.save()
        
        batch_id = self.client.createBatch(str(self.project_file.relative_to(self.network_root)), self.task_batch)
        self.client.resumeBatch(batch_id)
        self.client.disconnect()
        
        self.logger.info("Project file has been submitted to the pc cluster for processing...")
                    
        #self.doc = Metashape.Document() # needed to remove the lock on the project.    
        
def stamp_time(): #  - thank you UCDavis!
    '''
    Format the timestamps as needed
    '''
    stamp = datetime.datetime.now().strftime('%Y%m%dT%H%M')
    return stamp

# Used by add_gcps function - thank you UCDavis!
def _get_marker(chunk, label):
    for marker in chunk.markers:
        if marker.label == label:
            return marker
    return None

# Used by add_gcps function - thank you UCDavis!
def _get_camera(chunk, label):
    for camera in chunk.cameras:
        if camera.label.lower() == label.lower():
            return camera
    return None          