# ET-Correction-Tool
A python tool to automate the creation of the MIKE SHE evapotranspiration Dfs2 file from reference ET time-series at stations across the model domain and correct the reference ET data by a solar radiation factors, corresponding to the grid location and month of the year. 
![image](https://user-images.githubusercontent.com/42157509/125534670-98e5a83c-8cdb-4975-b895-25db333fc1bf.png)

Technical approach: 

Step 1: Read all the ET Dfs0s and create an ET time-series data frame. 

Step 2: Read the polygons shape file which define the zones with unique ET time-series. 

Step 3: Identify ET time-series for each polygon in the domain. 

![image](https://user-images.githubusercontent.com/42157509/125534903-701cac8a-5f9c-492d-9635-3e4480beb4c4.png)

Step 4: Identify all the solar radiation grid points inside a polygon. 

![image](https://user-images.githubusercontent.com/42157509/125534918-9e1934b3-5da6-4b99-9360-7284268a4fbd.png)

Step 5: Correct the ET time-series for the zone identified in step 4 for every grid point by the corresponding solar radiation factors for each month of the year and store the data in a NumPy array. Repeat this step for all the polygons. 

Step 6: Create a Dfs2 file based on - the corrected ET dataset (np array) generated in step 5; time span, timestep interval from the input ET Dfs0; grid size and projection system from the solar radiation correction factor input shapefile.  
