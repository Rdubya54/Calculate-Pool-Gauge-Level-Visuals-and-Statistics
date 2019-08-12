import arcpy
import os
import string
from arcpy import env
from arcpy.sa import *
import json as JSON

arcpy.env.overwriteOutput = True
arcpy.SetLogHistory(False)
arcpy.CheckOutExtension("3D")
arcpy.CheckOutExtension("spatial")

#get inputs from gui
CA=arcpy.GetParameterAsText(0)
unit=arcpy.GetParameterAsText(1)
pool_fc=arcpy.GetParameterAsText(2)
dem=arcpy.GetParameterAsText(3)
wcs=arcpy.GetParameterAsText(4)
wcs_name_field=arcpy.GetParameterAsText(5)
increment=arcpy.GetParameterAsText(6)
mxd_pointer=arcpy.GetParameterAsText(7)
env.workspace=arcpy.GetParameterAsText(8)
outputfolder=arcpy.GetParameterAsText(9)
food_plots=arcpy.GetParameterAsText(10)
food_plots_field=arcpy.GetParameterAsText(11)

def convert_list(listt):
        #remove blanks from export list
        listt=[x for x in listt if x != [[]]]
        string=str(listt)
        almost=string.replace("[","")
        there=almost.replace("]","")
        fixed="("+there+")"
        
        return fixed

#this function is used for identifying areas that while below the gauge level, will not be flooded due
#to other higher topography from allowing water to actually reach the area
def find_extraneous_polys(polygons,near_ref,counter,prev_adj_polygon_count):

##    arcpy.AddMessage(str(polygons))
##    arcpy.AddMessage(str(near_ref))
##    
    #calculate distance of polygons to current wcs
    arcpy.Near_analysis(polygons,near_ref)

    #copy near dist values into another field so values can be saved when near tool is run a second time
    arcpy.AddField_management(polygons,"NEAR_DIST"+str(counter)+str(wcs_name), "FLOAT")
    arcpy.CalculateField_management(polygons, "NEAR_DIST"+str(counter)+str(wcs_name), "!NEAR_DIST!", "PYTHON_9.3")

    extra="(NEAR_DIST1"+str(wcs_name)+"<5 AND NEAR_DIST1"+str(wcs_name)+">=0"

    for i in range(counter):
        if i>0:
            extra+=" OR NEAR_DIST"+str(i+1)+str(wcs_name)+"=0"

    #give a bit more ditance leeway on the first run because the pump point
    #may not be placed exactly where it should be 
    query=extra + ") AND gridcode<5"

    #isolate polygons that are adjacent to wcs
    iso_polys=arcpy.MakeFeatureLayer_management(polygons,"iso_polys",query,"","Habitat")
    arcpy.CopyFeatures_management(iso_polys,os.path.join(env.workspace,str(pool_name)+"_wcs"+str(wcs_name)+"_gauge"+replace+"_isoPolys"+str(counter)))

    counter+=1

    #counter number of polys identifed as adj
    adj_polygon_count=arcpy.management.GetCount(iso_polys)[0]
##    arcpy.AddMessage("counter:"+str(counter))
##    arcpy.AddMessage("prev adj"+str(prev_adj_polygon_count))
##    arcpy.AddMessage("adj"+str(adj_polygon_count))

    #check to see if this is the same as previous number of polys in adj polys feature class.
    #if it is the same it means no more new adj polys are out there to be found and we can
    #end the recursion process
    if int(adj_polygon_count)==int(prev_adj_polygon_count):
        #return number of times we recurred
##        arcpy.AddMessage("ending")
        return counter
    
    else:
        return find_extraneous_polys(polygons,iso_polys,counter,adj_polygon_count)

    
#this function is for getting a better estimation of where water enters the pool from the pump.
#this needs to be done because this is the elevation that the water is actually starting at so using
#the location of the wcs (this is what the wetland managers will) will not produce the most accurate outputs
#because they are not located where water enters the pool. Sometimes they are even situated on the levee which
#would create a very inaccurate output. To counteract this a 25m buffer will be placed over every wcs and the cell
#with the lowest elevation within that buffer will be used as the daylight estimation point
def estimate_daylight_point(dem,wcs,pool_name,wcs_name):

    arcpy.AddMessage("Estimating daylight point for "+str(wcs_name))

    #buffer all wcs
    buffers=os.path.join(env.workspace,str(pool_name)+"_"+str(wcs_name)+"_buffers")
    arcpy.Buffer_analysis(wcs, buffers , "25 Meters")

    #clip buffers to pool
    clipped_buffers=os.path.join(env.workspace,str(pool_name)+"_"+str(wcs_name)+"_clipped")
    arcpy.Clip_analysis(buffers,pool_fc,clipped_buffers)

    #convert polygon to raster
    raster_buffers=os.path.join(env.workspace,str(pool_name)+"_"+str(wcs_name)+"_raster_buffers")
    arcpy.PolygonToRaster_conversion(clipped_buffers, "OBJECTID", raster_buffers,"CELL_CENTER","",1)

    #convert raster inot points
    buffer_points=os.path.join(env.workspace,str(pool_name)+"_"+str(wcs_name)+"_buffer_points")
    arcpy.RasterToPoint_conversion(raster_buffers, buffer_points, "VALUE")

    #extract elevation values to points
    ExtractMultiValuesToPoints(buffer_points, [[dem, "Elev"]], "BILINEAR")

    #sort points so that min elevation is easy to find
    points_sorted=os.path.join(env.workspace,str(pool_name)+"_"+str(wcs_name)+"_points_sorted")
    arcpy.Sort_management(buffer_points, points_sorted, [["grid_code","ASCENDING"],["Elev", "ASCENDING"]])

    point_fields=["OBJECTID","grid_code"]

    point_list=[]

    prev_point_code=""

    #iterate through points, 
    with arcpy.da.SearchCursor(points_sorted,(point_fields)) as cursor:
        for point in cursor:

            #check if you are at a new buffer
            if prev_point_code!=point[1]:

                #wcs minimum has been located, add it to extraction list
                point_list.append(point[0])

            prev_point_code = point[1]

    point_list=convert_list(point_list)

    #make feature layer with only points in extraction list
    daylight_points=arcpy.MakeFeatureLayer_management(points_sorted,"selected_points","OBJECTID IN "+point_list)

    #save points in perm
    perm=os.path.join(env.workspace,str(pool_name)+"_"+str(wcs_name)+"_perm_points")
    arcpy.CopyFeatures_management(daylight_points,perm)

    return perm
    
#capitalize all letters in names to insure uniformity in json
CA=CA.upper()
unit=unit.upper()

#get the name of pool for saving 
base = os.path.splitext(str(pool_fc))[0]
basename=os.path.basename(base)
naming=basename.replace(" ", "_")
pool_name=naming.upper()

#clip dem to pool just in case it isnt already
pool_dem=os.path.join(env.workspace,str(naming)+"_dem")
arcpy.Clip_management(dem, '#', pool_dem, pool_fc, '#', 'ClippingGeometry')
dem=pool_dem

#create Raster object (necessary to get min and max)
raster = arcpy.Raster(dem)
minimum_elev=raster.minimum
maximum_elev=raster.maximum

#get OBJECTID field (necessary for being able to select wcs's individually
oid_fieldname = arcpy.ListFields(wcs,"","OID")[0].name
wcs_fields=[oid_fieldname,wcs_name_field,"valid"]

#create dicts for collecting data that will later be turned into a json at the end of script
ca_dict={}
unit_dict={}
pool_dict={}
wcs_dict={}

#add underscores to names for folder strucuture
CA=CA.replace(" ","_")
unit=unit.replace(" ","_")

#create final output folders
data_folder=outputfolder+'\\'+CA+"_"+pool_name
image_folder=data_folder+'\\'+CA+"_"+pool_name

#switch underscores back
CA=CA.replace("_"," ")
unit=unit.replace("_"," ")

try:
    data_folder=os.mkdir(data_folder)

except:
    arcpy.AddMessage("")

try:
    image_folder=os.mkdir(image_folder)

except:
    arcpy.AddMessage("")

#get total acres of input pool
pool_fields=["SHAPE@AREA"]
with arcpy.da.SearchCursor(pool_fc,(pool_fields)) as cursor:
    for row in cursor:
        total_acres=row[0]*0.00024710538147

#iterate through water control structures
with arcpy.da.SearchCursor(wcs,(wcs_fields)) as cursor3:

    for row in cursor3:

        wcs_name=str(row[1])
        wcs_name=wcs_name.replace(" ","_")
        wcs_name=wcs_name.upper()

        daylight_points=estimate_daylight_point(dem,wcs,pool_name,wcs_name)
        
        #reset gauge dict with every new wcs
        gauge_dict={}
        
        arcpy.AddMessage("Calculating for Water Control Structure "+str(wcs_name))

        #set gauge level to minimum elevation 
        gaugelevel=round(float(minimum_elev),2)
        gaugelevel=maximum_elev-0.01

        #isolate current water control structure
        current_wcs=arcpy.MakeFeatureLayer_management(daylight_points,"selected_Wecs",oid_fieldname+"="+str(row[0]))

        #keep outputting data until gauge level gets higher than maximum elevation
        while gaugelevel<maximum_elev:

            arcpy.AddMessage("  Calculating at gauge: "+str(gaugelevel))

            #begin process for calculating flooded area at specified gauge

            #Create the inital table that will be used to reclass the dem by
##            replace=string.replace(str(gaugelevel),".","_")
##            table=arcpy.CreateTable_management(env.workspace, str(naming)+"_"+str(wcs_name)+"_"+replace+"_"+"input_table")
##            
##            #add necessary fields to the newly created table
##            arcpy.AddField_management(table,"Table_Number", "TEXT")
##            arcpy.AddField_management(table,"FROM_", "FLOAT")
##            arcpy.AddField_management(table,"TO_", "FLOAT")
##            arcpy.AddField_management(table,"Gauge", "FLOAT")
##            arcpy.AddField_management(table,"OUT_", "INTEGER")
##            arcpy.AddField_management(table,"CLASSIFICATION", "STRING")
##
##            #Input the table number field
##            insert_fields=["Table_Number","FROM_","TO_","Gauge","OUT_"]
##            cursor = arcpy.da.InsertCursor(table, insert_fields)
##
##            i=1
##
##            for x in range(0, 5):
##                
##                cursor.insertRow(("Table" +str(i),0,0,gaugelevel,i))
##                i+=1
##
##            cursor.insertRow
##                
##            del cursor
##
##            #Input the TO/FROM and CLASSIFICATION fields
##
##            FROM_fields=["Table_Number","FROM_","TO_","CLASSIFICATION"]
##
##            #6 inches = 0.1524 meters
##            #this is where you are setting the gauge
##
##            with arcpy.da.UpdateCursor(table,(FROM_fields)) as cursor2:
##
##                for row in cursor2:
##
##                    if (row[0]=="Table1"):
##                        row[1]=0
##                        row[2]=(float(gaugelevel)-0.4572)
##                        row[3]="Fully Flooded, >18in"
##
##                    elif (row[0]=="Table2"):
##                        row[1]=(float(gaugelevel)-0.4572)
##                        row[2]=(float(gaugelevel)-0.3048)
##                        row[3]="Shallowly Flooded, 12-18in"
##                        
##                    elif (row[0]=="Table3"):
##                        row[1]=(float(gaugelevel)-0.3048)
##                        row[2]=(float(gaugelevel)-0.1524)
##                        row[3]="Shallowly Flooded, 6-12in"
##                        
##                    elif (row[0]=="Table4"):
##                        row[1]=(float(gaugelevel)-0.1524)
##                        row[2]=gaugelevel
##                        row[3]="Shallowly Flooded, 0-6in"
##
##                    elif (row[0]=="Table5"):
##                        row[1]=gaugelevel
##                        row[2]=1000
##                        row[3]="Dry, not flooded"
##
##                    cursor2.updateRow(row)
##
##            del cursor2
##
##            #Reclass input dem raster by these table values
##            raster_reclass=os.path.join(env.workspace,str(naming)+"_"+str(wcs_name)+"_"+replace+"_"+"Reclassed_Surface")
##            arcpy.ReclassByTable_3d(dem,table,"FROM_","TO_","OUT_",raster_reclass,"NODATA")
##
##            #we now have the pool reclassed properly by the guage, but water control structures need to be accounted for
##            #so we must
##            #convert output raster to polygons so that non adjacent areas below gauge level can be removed
##            polygons=os.path.join(env.workspace,str(naming)+"_"+str(wcs_name)+"_"+replace+"_"+"Raster_Polygons")
##            arcpy.RasterToPolygon_conversion(raster_reclass,polygons,"SIMPLIFY","VALUE")
##
##            #this fucntion finds those non adjacent areas below gauge level
##            near_run_count=find_extraneous_polys(polygons,daylight_points,1,0)
##
##            extra="(NEAR_DIST1"+str(wcs_name)+"<5 AND NEAR_DIST1"+str(wcs_name)+">=0"
##
##            for i in range(near_run_count-1):
##                if i>0:
##                    extra+=" OR NEAR_DIST"+str(i+1)+str(wcs_name)+"=0"
##
##            query=extra + ") AND gridcode<5"
##
##            flooded_polys=arcpy.MakeFeatureLayer_management(polygons,"final_polys",query)
##            arcpy.CopyFeatures_management(flooded_polys,os.path.join(env.workspace,str(pool_name)+"_wcs"+str(wcs_name)+"_gauge"+replace+"_Polys"))
##
##            #convert polygons back to raster data, an accurate representation of where the water will be at the specified gauge is now created
##            flooded_raster=os.path.join(env.workspace,str(pool_name)+"_wcs"+str(wcs_name)+"_gauge"+replace+"_floodedraster")
##            arcpy.PolygonToRaster_conversion(flooded_polys, "gridcode", flooded_raster,"MAXIMUM_AREA","", 1)
##
##            ####################################FOOD PLOT PART #######################################################################
##            if (food_plots):
##
##                #sort food plots by crop type so it is easy to iterate through them while skipping repeats (move this to begenning of code later)
##                plots_sorted=os.path.join(env.workspace,str(pool_name)+"_sorted_plot")
##                arcpy.Sort_management(food_plots, plots_sorted, [["Crop", "ASCENDING"]])
##
##                food_fields=["Crop"]
##
##                crop_dict_master={}
##
##                #iterate through every food plot, selecting by crop
##                with arcpy.da.SearchCursor(plots_sorted,(food_fields)) as cursor3:
##
##                    prev_crop=""
##                    
##                    for row in cursor3:
##                        crop_name=row[0].replace(" ", "_")
##                        crop=row[0]
##
##                        #if below process hasnt been run for this crop type et                    
##                        if (prev_crop != crop):
##
##                            crop_dict={}
##                            total_crop_acres=0
##
##                            #make feature layer of only current crop
##                            current_crop=arcpy.MakeFeatureLayer_management(food_plots,"selected_plots","Crop='"+crop+"'")
##                            arcpy.CopyFeatures_management(current_crop, os.path.join(env.workspace,"current_crop"+crop_name))
##
##                            #get total acres of crop
##                            crop_fields=["SHAPE@AREA"]
##                            with arcpy.da.SearchCursor(current_crop,(crop_fields)) as cursor:
##                                for row in cursor:
##                                    total_crop_acres+=row[0]*0.00024710538147
##
##                            #clip crop polygons to flood raster classified as water
##                            flooded_clip=os.path.join(env.workspace,str(pool_name)+"_wcs"+str(wcs_name)+"_gauge"+replace+"_"+crop_name+"_flooded_clip")
##                            arcpy.Clip_management(flooded_raster, '#',flooded_clip, current_crop, '#', 'ClippingGeometry')
##
##                            #raster to polygon output
##                            crop_polys=os.path.join(env.workspace,str(naming)+"_"+str(wcs_name)+"_"+replace+"_"+crop_name+"_"+"Clip_Polygons")
##
##                            #if this line fails its because there was no flooded crop
##                            try:
##                                arcpy.RasterToPolygon_conversion(flooded_clip,crop_polys,"SIMPLIFY","VALUE")
##                                flooded_crop=True
##
##                            except:
##                                flooded_crop=False
##
##                            crop_dict["Full_Flooded_18in"]="0"
##                            crop_dict["Shallowly_Flooded_12_18in"]="0"
##                            crop_dict["Shallowly_Flooded_6-12in"]="0"
##                            crop_dict["Shallowly_Flooded_0_6in"]="0"
##
##                            if (flooded_crop==True):
##                                    
##                                #select output by each flooded type
##                                for x in range(1, 6):
##                                    
##                                    current_flood=arcpy.MakeFeatureLayer_management(crop_polys,"selected_stage","gridcode="+str(x))
##
##                                    #sum Shape_Area and convert to Acres
##                                    summary_table=os.path.join(env.workspace,str(naming)+"_"+str(wcs_name)+"_"+replace+"_"+crop_name+str(x)+"_"+"sumtable")
##                                    arcpy.Statistics_analysis(current_flood, summary_table, [["Shape_Area", "SUM"]])
##
##                                    sum_fields=["SUM_Shape_Area"]
##                                    with arcpy.da.SearchCursor(summary_table,(sum_fields)) as table:
##                                        for row in table:
##                                            total_acreage=row[0]*0.00024710538147
##                                            if (x==1):
##                                                flood_class="Full_Flooded_18in"
##                                            elif (x==2):
##                                                flood_class="Shallowly_Flooded_12_18in"
##                                            elif (x==3):
##                                                flood_class="Shallowly_Flooded_6-12in"
##                                            elif (x==4):
##                                                flood_class="Shallowly_Flooded_0_6in"
##
##                                            crop_dict[flood_class]=str(round(float(total_acreage),2))
##                                            break
##                                        
##                                    #calculate total dry area
##                                    arcpy.AddMessage(str(crop))
##                                    arcpy.AddMessage("0-6:"+str(crop_dict["Shallowly_Flooded_0_6in"]))
##                                    arcpy.AddMessage("6-12:"+str(crop_dict["Shallowly_Flooded_6-12in"]))
##                                    arcpy.AddMessage("12-18:"+str(crop_dict["Shallowly_Flooded_12_18in"]))
##                                    arcpy.AddMessage("18:"+str(crop_dict["Full_Flooded_18in"]))
##                                    arcpy.AddMessage("total acres:"+str(round(float(total_crop_acres),2)))
##                                    arcpy.AddMessage("sum is"+str(float(crop_dict["Full_Flooded_18in"])+float(crop_dict["Shallowly_Flooded_12_18in"])+float(crop_dict["Shallowly_Flooded_6-12in"])+float(crop_dict["Shallowly_Flooded_0_6in"])))
##                                        
##                                    crop_dict["Dry_not_flooded"]=str(round(float(total_crop_acres),2)-(float(crop_dict["Full_Flooded_18in"])+float(crop_dict["Shallowly_Flooded_12_18in"])+float(crop_dict["Shallowly_Flooded_6-12in"])+float(crop_dict["Shallowly_Flooded_0_6in"])))
##
##                                    if (float(crop_dict["Dry_not_flooded"])<0):
##                                        crop_dict["Dry_not_flooded"]=str(0.0)
##
##                                    crop_dict["Dry_not_flooded"]=str(round(float(crop_dict["Dry_not_flooded"]),2))
##                                    arcpy.AddMessage("Dry not flooded:"+str(crop_dict["Dry_not_flooded"]))
##                                    arcpy.AddMessage("Total crop acres:"+str(round(float(total_crop_acres),2)))
##
##                            #this is when no crops were flooded and code just needs all 0's
##                            else:
##                                crop_dict["Dry_not_flooded"]=str(round(float(total_crop_acres),2))
##
##
##                            crop_dict["Total Acres"]=str(round(float(total_crop_acres),2))
##        
##                            #amount of acres flooded for this crop is now complete, codes moves on to next crop
##                            
##                            #save crop name to prevent repeat iterations
##                            prev_crop=crop
##
##                            crop_dict_master[crop_name]=crop_dict
##                       
##                            #if same crop as before do nothing
##
##                del cursor3
##
##            #######################################################End food plot#####################################################################
##
##
##            ##############creating the data for the gauge level visual is now done######################
##                
##            #############now stats need to be calculated for the gauge level###############################################################################
##
##            #calculate area of each polygon by acres
##
##            arcpy.AddField_management(flooded_polys,"ACRES", "FLOAT")
##
##            arcpy.CalculateField_management(flooded_polys, "ACRES",'!Shape_Area!*0.00024710538147', "PYTHON_9.3")
##
##            #add habitat field and determine it according to gridcode
##            arcpy.AddField_management(flooded_polys,"Habitat", "TEXT")
##
##            hab_fields=["gridcode","Habitat"]
##
##            with arcpy.da.UpdateCursor(flooded_polys,(hab_fields)) as cursor3:
##
##                for row in cursor3:
##
##                    if (row[0]==1):
##                        row[1]="Full_Flooded_18in"
##                    
##                    elif (row[0]==2):
##                        row[1]="Shallowly_Flooded_12_18in"
##                            
##                    elif (row[0]==3):
##                        row[1]="Shallowly_Flooded_6_12in"
##
##                    elif (row[0]==4):
##                        row[1]="Shallowly_Flooded_0_6in"
##                            
##                    elif (row[0]==5):
##                        row[1]="Dry_not_flooded"
##                            
##                    cursor3.updateRow(row)
##
##            del cursor3
##
##            #Add fields for gauge_level, Water Control Structure, and Pool Name. 
##            arcpy.AddField_management(flooded_polys,"Gauge_Level", "FLOAT")
##            arcpy.AddField_management(flooded_polys,"BasnStrctr", "TEXT")
##            arcpy.AddField_management(flooded_polys,"Pool_Name", "TEXT")
##
##            try:
##
##                arcpy.DeleteField_management(flooded_polys,"ID")
##
##            except:
##                arcpy.AddMessage("")
##
##            pop_fields=["Gauge_Level","BasnStrctr","Pool_Name"]
##
##            with arcpy.da.UpdateCursor(flooded_polys,(pop_fields)) as cursor4:
##
##                for row in cursor4:
##
##                    row[0]=gaugelevel
##                    row[1]=wcs
##                    row[2]=pool_name
##
##                    cursor4.updateRow(row)
##
##            del cursor4
##
##            #Find total acres per habitat area
##            outtable=os.path.join(env.workspace,str(pool_name)+"_wcs"+str(wcs_name)+"_gauge"+replace+"_Stats")
##            arcpy.Statistics_analysis(flooded_polys, outtable,[["Acres", "SUM"]],"Habitat")
##
##            ###############################statistics are now also sucessfully calculated######################################
##            ##################################now the visuals and statstics for the guague need to be exported #######################
##            #####################################this will be done by screenshotting final raster and outputting statistics to json#############
##
##            #create dict for storing all starts
##            stats_dict={}
##
##            #create dict for storing habitat stats
##            habitat_dict={}
##            habitat_dict["Full_Flooded_18in"]="0"
##            habitat_dict["Shallowly_Flooded_12_18in"]="0"
##            habitat_dict["Shallowly_Flooded_6_12in"]="0"
##            habitat_dict["Shallowly_Flooded_0_6in"]="0"
##
##            #iterate through Stats table and add data to json object
##            #to make an easy to walk through json, we will make a habitat dict and put it inside of a guauge level dict
##            table_fields=["Habitat","SUM_ACRES"]
##            with arcpy.da.SearchCursor(outtable,(table_fields)) as cursor5:
##
##                for row in cursor5:
##                    habitat_dict[row[0]]=str(round(float(row[1]),2))
##
##                #add total acers and total acres dry to dict  
##                habitat_dict["Total_Acres"]=str(round(float(total_acres),2))
##                habitat_dict["Dry_not_flooded"]=str(round(float(total_acres),2)-round(float((float(habitat_dict["Full_Flooded_18in"])+float(habitat_dict["Shallowly_Flooded_12_18in"])+float(habitat_dict["Shallowly_Flooded_6_12in"])+float(habitat_dict["Shallowly_Flooded_0_6in"]))),2))
##                
##            del cursor5
##
##            #add habitat_dict to stats dict
##            stats_dict["Flooded_Habitat_By_Acres"]=habitat_dict
##
##            
##            if (food_plots):
##                stats_dict["Flooded_Crop_Stats_By_Acre"]=crop_dict_master
##            
##
##            #add name of corresponding image of pool at current gauge level
##            base = os.path.basename((raster_reclass))
##            stats_dict["Image_Name"]=base
            
            #create map document object and data frame object
            mxd = arcpy.mapping.MapDocument(str(mxd_pointer))
            df = arcpy.mapping.ListDataFrames(mxd)[0]

            layers=arcpy.mapping.ListLayers(df)

            #get symbology from these layers so that symbology of our output is uniform
            for lyr in layers:
##                if lyr.name.lower() == "reclassed surface":
##
##                    sourceLayer=lyr

                if lyr.name.lower() == "water control structures":
                    wcs_symbology_layer=lyr

                if lyr.name.lower() == "food plots":
                    plots_symbology_layer=lyr

##            #add newly calculated reclassed surface layer to mxd used for snapping screenshots
##            result=arcpy.MakeRasterLayer_management(flooded_raster, "current_raster")
##            layer = result.getOutput(0)
##
##            #add proper symbology to layer
##            arcpy.mapping.UpdateLayer(df, layer, sourceLayer, True)
##            arcpy.mapping.AddLayer(df, layer, "TOP")
##
##            #add wcs layer to mxd used for snapping screenshots


            #add proper symbology to layer
            wcs_layer=arcpy.mapping.Layer(wcs)      
            arcpy.mapping.UpdateLayer(df, wcs_layer,wcs_symbology_layer, True)
            arcpy.mapping.AddLayer(df, wcs_layer, "TOP")
            layers=arcpy.mapping.ListLayers(mxd,wcs_layer)[0]
            for lyr in layers.labelClasses:
                lyr.showClassLabels=True   
            layers.showLabels=True

            #add crop layer to mxd (if present)
            if (food_plots):
                plots_layer=arcpy.mapping.Layer(food_plots)
                arcpy.mapping.UpdateLayer(df, plots_layer,plots_symbology_layer, True)
                arcpy.mapping.AddLayer(df, plots_layer, "TOP")
                layers=arcpy.mapping.ListLayers(mxd,plots_layer)[0]
                for lyr in layers.labelClasses:
                     lyr.showClassLabels=True   
                layers.showLabels=True

            arcpy.RefreshActiveView()  
            arcpy.RefreshTOC()

            mxd.save()

            del mxd

            #reopen mxd and and get screenshot (there must be done or new layers
            #arent there)

            mxd = arcpy.mapping.MapDocument(str(mxd_pointer))
            df = arcpy.mapping.ListDataFrames(mxd)[0]
            layers=arcpy.mapping.ListLayers(df)

            #toggle food plots layer to visible bc for some reason it isnt by default
            for lyr in layers:
                if (lyr.name==food_plots):
                    lyr.visible=True

            arcpy.RefreshActiveView()  
            arcpy.RefreshTOC()
            
            #take screenshot of final raster for the gauge level and save to output folder
            ext = plots_layer.getExtent() 
            df.extent = ext
            path=os.path.join(image_folder,str(base))
            arcpy.AddMessage("PATH:"+path)
            arcpy.mapping.ExportToJPEG(mxd,path,df)

            del mxd

            #go back and delete layers that were added to basemap so that basemap stays
            #consitant
            mxd = arcpy.mapping.MapDocument(str(mxd_pointer))
            df = arcpy.mapping.ListDataFrames(mxd)[0]

            layers=arcpy.mapping.ListLayers(df)

            for lyr in layers:

                if (lyr.name == food_plots or lyr.name == wcs):
                    arcpy.mapping.RemoveLayer(df,lyr)
                    
                if (lyr.name=="current_raster"):
                    arcpy.mapping.RemoveLayer(df,lyr)

            arcpy.RefreshActiveView()  
            arcpy.RefreshTOC()

            mxd.save()

            del mxd
            
##            #add stats_dict into gauge_dict with corresponding gauge level as dict index
##            gauge_dict[str(gaugelevel)]=stats_dict
##
            #increment gauge level 
            gaugelevel=gaugelevel+float(increment)
##
##            #everything is now done at this gaugelevel
##            #all these steps will be repeated for each gauge level until max elevation for pool is reached
##
##        #when iterating through gaugle levels is done,
##        #add gaugle level dict to wcs dict
##        wcs_name.replace('_',' ')
##        wcs_dict[wcs_name]=gauge_dict
##
###when iterating through wcs's is done,
###add wcs_dict to pool_dict
##pool_name.replace('_',' ')
##pool_dict[pool_name]=wcs_dict
##
###add pool dict to unit dict
##unit_dict[unit]=pool_dict
##
###add unit dict to conservation area dict
##ca_dict[CA]=unit_dict
##
###save final output json to output folder
##output_file=os.path.join(data_folder,"data.json")
##with open(output_file, 'w') as outfile:
##    JSON.dump(ca_dict, outfile)

##layers=arcpy.mapping.ListLayers(mxd,"BB_2_WCS")[0]
##for lyr in layers.labelClasses:
##        lyr.showClassLabels=True   
##layers.showLabels=True
##arcpy.RefreshActiveView()
