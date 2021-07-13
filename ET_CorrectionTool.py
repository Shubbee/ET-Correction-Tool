"""
ET Correction Tool:

This script creates evapotranspiration Dfs2 from single/multiple reference ET
time-series, and applies spatially, monthly varying solar radiation correction 
factors to the reference ET data and creates the MIKE SHE input ET Dfs2 file.

Created on Wed Apr 28 15:50:07 2021

@author: Shubhneet Singh 
ssin@dhigroup.com
DHI,US

"""
# marks dependencies

import os
import clr
import sys
import time
import numpy as np #
import pandas as pd #
import datetime as dt
import shapefile #pyshp

from winreg import ConnectRegistry, OpenKey, HKEY_LOCAL_MACHINE, QueryValueEx

def get_mike_bin_directory_from_registry():
    x86 = False
    dhiRegistry = "SOFTWARE\Wow6432Node\DHI\\"
    aReg = ConnectRegistry(None, HKEY_LOCAL_MACHINE)
    try:
        _ = OpenKey(aReg, dhiRegistry)
    except FileNotFoundError:
        x86 = True
        dhiRegistry = "SOFTWARE\Wow6432Node\DHI\\"
        aReg = ConnectRegistry(None, HKEY_LOCAL_MACHINE)
        try:
            _ = OpenKey(aReg, dhiRegistry)
        except FileNotFoundError:
            raise FileNotFoundError
    year = 2030
    while year > 2010:
        try:
            mikeHomeDirKey = OpenKey(aReg, dhiRegistry + str(year))
        except FileNotFoundError:
            year -= 1
            continue
        if year > 2020:
            mikeHomeDirKey = OpenKey(aReg, dhiRegistry + "MIKE Zero\\" + str(year))

        mikeBin = QueryValueEx(mikeHomeDirKey, "HomeDir")[0]
        mikeBin += "bin\\"

        if not x86:
            mikeBin += "x64\\"

        if not os.path.exists(mikeBin):
            print(f"Cannot find MIKE ZERO in {mikeBin}")
            raise NotADirectoryError
        return mikeBin

    print("Cannot find MIKE ZERO")
    return ""

sys.path.append(get_mike_bin_directory_from_registry())
clr.AddReference("DHI.Generic.MikeZero.DFS")
clr.AddReference("DHI.Generic.MikeZero.EUM")
clr.AddReference("DHI.Projections")

from mikeio import * #
from mikeio.eum import ItemInfo
from shapely.geometry import Polygon, Point #

from tkinter import Frame, Label, Button, Entry, Tk, W, END
from tkinter import messagebox as tkMessageBox
# from tkinter.filedialog import askdirectory
from tkinter.filedialog import askopenfilename
from tkinter.filedialog import asksaveasfilename

#------------------------------------------------------------------------------
## File locations for testing tool:
# PolygonsShapefileName = r"C:\Users\ssin\OneDrive - DHI\Desktop\MIKE SHE ET\RefET_Prucha\NLDASzones3.shp"
# SolarRadiationShapefileName = r"C:\Users\ssin\OneDrive - DHI\Desktop\MIKE SHE ET\RefET_Prucha\SolarRad_SCALING_bymonth.shp"
# refDfs0path= r"C:\Users\ssin\OneDrive - DHI\Desktop\MIKE SHE ET\RefET_Prucha\PET_NLDAS2000_2020_1st10.dfs0"
# projpath = r"C:\Users\ssin\OneDrive - DHI\Desktop\MIKE SHE ET\RefET_Prucha\SolarRad_SCALING_bymonth.prj"
# filePath = r"C:\Users\ssin\OneDrive - DHI\Desktop\MIKE SHE ET\RefET_Prucha\Test.dfs2"
#------------------------------------------------------------------------------

# Read reference ET Dfs0 file(s), and create a dataframe: 
def ReferenceET2Dataframe(refDfs0path):
    
    ReferenceET_Directory = os.path.dirname(refDfs0path)
    os.chdir(ReferenceET_Directory)
    input_file_names = os.listdir(ReferenceET_Directory)   
    ReferenceET_File_Names = [filenames for filenames in input_file_names 
                      if filenames.endswith('dfs0')] 

    ReferenceET_df = pd.DataFrame()
   
    for num_ET in range(len(ReferenceET_File_Names)):
        ReferenceET_dfs0 = Dfs0(ReferenceET_File_Names[num_ET]).to_dataframe()
        ReferenceET_df = pd.concat([ReferenceET_df, ReferenceET_dfs0], axis=1)
    return ReferenceET_df

# Reference ET metadata for creating Dfs2: 
def RefETMetadata(refDfs0path):
           
    ReferenceET_df = ReferenceET2Dataframe(refDfs0path)
    metadata_file = Dfs0(refDfs0path)
    ETMetadata = {
        "NumStations" : ReferenceET_df.shape[1],
        "Type" : metadata_file.items[0].type,
        "Unit" : metadata_file.items[0].unit,
        "StartTime" : ReferenceET_df.index[0],
        "NumTimesteps" : len(ReferenceET_df.index),
        "Timestep" : (ReferenceET_df.index[1]-ReferenceET_df.index[0]).total_seconds(),
        "Max" : round(ReferenceET_df.max().max(),2),
        "MaxStation" : ReferenceET_df.max().idxmax(),
        "MaxTimestep" : ReferenceET_df.idxmax()[ReferenceET_df.max().idxmax()]
        }
    return ETMetadata
    print('Maximum ET in reference data is '+str(ETMetadata.Max)+' ' +str(ETMetadata.Unit)[8:] + 
          ' at station '+ str(ETMetadata.MaxStation) + ' on ' + str(ETMetadata.MaxTimestep))

#Read correction factor grid shape file:
def Correction_df(SolarRadiationShapefileName):

    SolarRadiation_Shapefile = shapefile.Reader(SolarRadiationShapefileName)
    SolarRadiation_fields = [field[0] for field
                             in SolarRadiation_Shapefile.fields[1:]]
    
    SolarRadiation_fields[2:14] = [dt.date(2000, month, 1).strftime('%B') 
                                   for month in range(1,13)] #Month Names
    
    SolarRadiation_records = SolarRadiation_Shapefile.records()
    SolarRadiation_df = pd.DataFrame(columns = SolarRadiation_fields,
                                     data = SolarRadiation_records)
    Grid_X = SolarRadiation_df.X.sort_values(ascending = True).unique()
    Grid_Y = SolarRadiation_df.Y.sort_values(ascending = False).unique()
    
    return SolarRadiation_df, Grid_X, Grid_Y

 
# Correct ref ET by scaling factors and create ET Dfs2 input data nparray:
def ETCorrection(PolygonsShapefileName, SolarRadiationShapefileName, refDfs0path):
    
    # Input ref ET in dataframe
    ReferenceET_df = ReferenceET2Dataframe(refDfs0path)
    
    # Ref ET polygons reading:
    Polygons_Shapefile = shapefile.Reader(PolygonsShapefileName)
    #Excluding deletion flag
    Polygons_Shapefile_fieldnames = [field[0] for field 
                                     in Polygons_Shapefile.fields[1:]] 
    
    for index in range(len(Polygons_Shapefile_fieldnames)):  
        if Polygons_Shapefile_fieldnames[index] == 'ETStation':
            ETStation_field_index = index 
    
    Attribute_table = Polygons_Shapefile.records()
    ETStation_Names = [Polygons_Shapefile.record(record)[ETStation_field_index] 
                       for record in range(len(Attribute_table))]
    
    Num_Polygons = len(Polygons_Shapefile.shapes())
    Polygons_Coordinates = [Polygons_Shapefile.shape(poly).points 
                           for poly in range(Num_Polygons)]  
    
    # Correction factor grid reading
    SolarRadiation_df, Grid_X, Grid_Y = Correction_df(SolarRadiationShapefileName)
    
    #Find points inside every polygon:
    ListPointsinPolygons = [[] for poly in range(len(Polygons_Coordinates))]
    
    for loc in range(len(SolarRadiation_df)):
        SolarRadiation_point = Point(SolarRadiation_df.X[loc],
                                     SolarRadiation_df.Y[loc]) #shapely point
    
        for poly in range(len(Polygons_Coordinates)):
            ET_Polygon = Polygon(Polygons_Coordinates[poly]) #shapely polygon
            
            if ET_Polygon.contains(SolarRadiation_point):
                ListPointsinPolygons[poly].append(loc)  # Self Note: check point on poly line

    print('Solar radiation points inside each ET polygon identified')  
    
    # Define output corrected data array:
    Corrected_ET =  np.zeros((len(ReferenceET_df),
                              len(Grid_Y),
                              len(Grid_X)))
    
    # Corrected_ET =  np.zeros((1, 
    #                       len(Grid_Y), 
    #                       len(Grid_X)))
    
    # Correction of ET data looping all polygons, identifying their ref ET
    for poly in range(len(Polygons_Coordinates)):
    
        ThisPolygon_ReferenceET = ReferenceET_df[ETStation_Names[poly]]  #[0:1]
        ThisPolygon_ReferenceET_Copy = ThisPolygon_ReferenceET.copy()
        
        # Correction of all points within the polygon in loop
        for point_index in ListPointsinPolygons[poly]:
            
            for month in range(1,13):
               ThisPoint_CorrectionFactor = SolarRadiation_df.iloc[point_index,
                                                                    month+1]
               This_month_index = ThisPolygon_ReferenceET_Copy.index.month==month
               
               # Correction of ref ET for a grid point with correcponding correction factor
               if len(This_month_index) !=0:
                   This_month_values = ThisPolygon_ReferenceET[This_month_index].copy()
                   ThisPolygon_ReferenceET_Copy[This_month_index] = ThisPoint_CorrectionFactor * This_month_values    
                          
            #Define spatial location for corrected ET time-series of a grid point
            for x in range(len(Grid_X)):
                if SolarRadiation_df.X[point_index] == Grid_X[x]:
                    X=x
                    break
            for y in range(len(Grid_Y)):
                if SolarRadiation_df.Y[point_index] == Grid_Y[y]:
                    Y=y
                    break
            # Store corrected ET time-series      
            Corrected_ET[:,Y,X] = ThisPolygon_ReferenceET_Copy
        print('Grid points in polygon > '+ str(poly) +' corrected for solar radiation') 
            
    return Corrected_ET
       

# Write Dfs2 ouput file:
def buildETDfs(filePath, Corrected_ET, SolarRadiationShapefileName, projpath, refDfs0path):
    if os.path.exists(filePath):
        os.remove(filePath)
    dfs = Dfs2()
    #Projection sys from shape file
    projString = open(projpath, "r").read()
    
    #ET timeseries data
    ETMetadata = RefETMetadata(refDfs0path)

    SolarRadiation_df, Grid_X, Grid_Y = Correction_df(SolarRadiationShapefileName)
    Dx = Grid_X[1]-Grid_X[0]
    Dy = Grid_Y[0]-Grid_Y[1]

    dfs.write(filename = filePath,
              data = [Corrected_ET],
              start_time = ETMetadata["StartTime"],
              dt = ETMetadata["Timestep"], 
              items=[ItemInfo("Evapotranspiration", 
                              ETMetadata["Type"],
                              ETMetadata["Unit"],
                              data_value_type='Instantaneous')],
              dx = Dx,
              dy = Dy,
              coordinate = [projString,
                            Grid_X[0],
                            Grid_Y[-1],
                            0],
              title="ET_RadiationCorrected")
    print('Dfs2 created')    

def ETCorrectionTool(refDfs0path, PolygonsShapefileName, SolarRadiationShapefileName, projpath, filePath):
    
    Tool_start_time = time.time()    
    Corrected_ET = ETCorrection(PolygonsShapefileName, SolarRadiationShapefileName, refDfs0path)
    
    Dfs2_start_time = time.time()   
    buildETDfs(filePath, Corrected_ET, SolarRadiationShapefileName, projpath, refDfs0path)
    print('Writing time' + "- %s seconds" % (time.time() - Dfs2_start_time))
    
    print('Total time'+"- %s seconds" % (time.time() - Tool_start_time))
    
#------------------------------------------------------------------------------
# UI for this tool:
     
class interface(Frame):
    def __init__(self, master = None):
        """ Initialize Frame. """
        Frame.__init__(self,master)
        self.grid()
        self.createWidgets()
            
    def message(self):
        tkMessageBox.showinfo("Task Completed", "Reference ET data corrected!")
    
    def run(self):
        
        # input1 - Ref ET timeseries in Dfs0:
        filename1 = self.file_name1.get()
        # input2 - Polygons for every ET timeseries in shp file:
        filename2 = self.file_name2.get()
        # input3 - Correction factor grid with monthly values in shape file:
        filename3 = self.file_name3.get()
        # input4 - Projection file:
        filename4 = self.file_name4.get()
        # Output:
        outputFile = self.file_name5.get()
        # Tool
        ETCorrectionTool(filename1, filename2, filename3, filename4, outputFile)        
        
        self.message()
        

    def createWidgets(self):
        
        # set all labels of inputs:
        Label(self, text = "Note: Output Dfs2's start time, time steps, and ET data units will be same as reference ET Dfs0")\
            .grid(row=0, columnspan=3,sticky=W)
        Label(self, text = "Reference ET (*.dfs0) :")\
            .grid(row=1, column=0, sticky=W)
        Label(self, text = "ET Polygons (*.shp) :")\
            .grid(row=2, column=0, sticky=W)
        Label(self, text = "Solar Radiation Factors (*.shp) :")\
            .grid(row=3, column=0, sticky=W)            
        Label(self, text = "Projection (*.prj) :")\
            .grid(row=4, column=0, sticky=W)
        Label(self, text = "Output Corrected ET (*.dfs2) :")\
            .grid(row=5, column=0, sticky=W)
            
        # set buttons
        Button(self, text = "Browse", command=self.load_file1, width=10)\
            .grid(row=1, column=6, sticky=W)
        Button(self, text = "Browse", command=self.load_file2, width=10)\
            .grid(row=2, column=6, sticky=W)
        Button(self, text = "Browse", command=self.load_file3, width=10)\
            .grid(row=3, column=6, sticky=W)
        Button(self, text = "Browse", command=self.load_file4, width=10)\
            .grid(row=4, column=6, sticky=W)
        Button(self, text = "Save As", command=self.load_file5, width=10)\
            .grid(row=5, column=6, sticky=W)            
        Button(self, text = "Run ET Correction", command=self.run, width=20)\
            .grid(row=6, column=2, sticky=W)
       
        # set entry field
        self.file_name1 = Entry(self, width=65)
        self.file_name1.grid(row=1, column=1, columnspan=4, sticky=W)
        self.file_name2 = Entry(self, width=65)
        self.file_name2.grid(row=2, column=1, columnspan=4, sticky=W)
        self.file_name3 = Entry(self, width=65)
        self.file_name3.grid(row=3, column=1, columnspan=4, sticky=W)       
        self.file_name4 = Entry(self, width=65)
        self.file_name4.grid(row=4, column=1, columnspan=4, sticky=W)
        self.file_name5 = Entry(self, width=65)
        self.file_name5.grid(row=5, column=1, columnspan=4, sticky=W)

    def load_file1(self):
        self.filename = askopenfilename(initialdir=os.path.curdir)
        if self.filename: 
            try: 
                #self.settings.set(self.filename)
                self.file_name1.delete(0, END)
                self.file_name1.insert(0, self.filename)
                self.file_name1.xview_moveto(1.0)
            except IOError:
                tkMessageBox.showerror("Error","Failed to read file \n'%s'"%self.filename) 
   
    def load_file2(self):
        self.filename = askopenfilename(initialdir=os.path.curdir)
        if self.filename: 
            try: 
                #self.settings.set(self.filename)
                self.file_name2.delete(0, END)
                self.file_name2.insert(0, self.filename)
                self.file_name2.xview_moveto(1.0)
            except IOError:
                tkMessageBox.showerror("Error","Failed to read file \n'%s'"%self.filename) 
                
    def load_file3(self):
        self.filename = askopenfilename(initialdir=os.path.curdir)
        if self.filename: 
            try: 
                #self.settings.set(self.filename)
                self.file_name3.delete(0, END)
                self.file_name3.insert(0, self.filename)
                self.file_name3.xview_moveto(1.0)
            except IOError:
                tkMessageBox.showerror("Error","Failed to read file \n'%s'"%self.filename) 
    
    def load_file4(self):
        self.filename = askopenfilename(initialdir=os.path.curdir)
        if self.filename: 
            try: 
                #self.settings.set(self.filename)
                self.file_name4.delete(0, END)
                self.file_name4.insert(0, self.filename)
                self.file_name4.xview_moveto(1.0)
            except IOError:
                tkMessageBox.showerror("Error","Failed to read file \n'%s'"%self.filename)                
                
                
    def load_file5(self):
        self.filename = asksaveasfilename(initialdir=os.path.curdir,defaultextension=".dfs2", filetypes=(("Dfs2 File", "*.dfs2"),("All Files", "*.*") ))
        if self.filename: 
            try: 
                #self.settings.set(self.filename)
                self.file_name5.delete(0, END)
                self.file_name5.insert(0, self.filename)
                self.file_name5.xview_moveto(1.0)
            except IOError:
                tkMessageBox.showerror("Error","Failed to read file \n'%s'"%self.filename) 
                
##### main program


root = Tk()
UI = interface(master=root)
UI.master.title("Evapotranspiration Correction Tool")
UI.master.geometry('680x270')
for child in UI.winfo_children():
    child.grid_configure(padx=4, pady =6)
    
UI.mainloop()
