# Image processing scripts using Python

This repo contains various Python scripts that are used for image processing, in particular those useful for photogrammetry.
As a result, the scripts are designed with the standardised Agisoft Metashape Python workflow in mind, utilising a fully compatible YML configuration file

## Requirements & setup
**Python**: You need Python (3.5, 3.6, 3.7, or 3.8), and I recommend using the Anaconda distribution and a processing-specific Anaconda environment.
At the bare minimum the following libraries should be installed besides the standard libs:
- numpy
- pandas
- opencv2

**How to use**: Simply clone this repository to your machine!

## Usage
Either run the scripts through the command line or run it manually.
When running through the CLI:

`python {repo_path}/python/{script}.py {config_path}/{config_file}.yml`

### File organisation
Output from foreground extraction:
```
project_photos
├───100MEDIA
|       DJI_0001.JPG
|       DJI_0002.JPG
|       ...
├───.100MEDIA_original
        DJI_0001.JPG
        DJI_0002.JPG
        ...
```

Output from marker identification:
```
project_photos
├───100MEDIA
|       DJI_0001.JPG
|       DJI_0002.JPG
|       ...
├───101MEDIA
|       DJI_0001.JPG
|       DJI_0002.JPG
|       ...
├───102MEDIA
|       DJI_0001.JPG
|       DJI_0002.JPG
|       ...
├───gcps
        prepared
               gcp_imagecoords_table.csv
               gcp_table.csv
```

### Workflow configuration

All of the parameters defining the Metashape workflow are specified in a YAML configuration file.
This includes directories of input and output files, workflow steps to include, quality settings, and many other parameters.
This configuration file is compatible with the UC Davis standardised Agisoft Metashape workflow.

An example configuration file is provided in this repo at `config/example.yml`. 
The file contains comments explaining the purpose of each customizable parameter.
To prepare a customized workflow, copy the `config/example.yml` file to a new location, edit the parameter values to meet your specifications, save it, and then run the Python script from the command line as described above, passing it the location of the customized configuration file. 
Do not remove or add parameters to the configuration file; adding will have no effect unless the Python code is changed along with the addition, and removing will produce errors.

The workflow configuration is saved in a procesing log at the end of a workflow run (see below).