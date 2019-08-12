import firebase_admin
import google.cloud
from firebase_admin import credentials, firestore, storage
import json
import os


###############################inputs##################################################
path_to_private_key='C:\Users\Ryan Wortmann\Desktop\Watefowl_tool_Python\Duck_Creek_BB_1\waterfowltool-firebase-adminsdk-cdwex-65c95dee9f.json'
path_to_json='C:\Users\Wortmr\OneDrive - Missouri Department of Conservation\Waterfowl_Wetland_Data_Management\output_jpegs9\BK_LEECH_BB_2\data.json'
path_to_folder_of_images='C:\Users\Wortmr\OneDrive - Missouri Department of Conservation\Waterfowl_Wetland_Data_Management\output_jpegs9\BK_LEECH_BB_2\BK_LEECH_BB_2'

##########################################################################################

#point script to the certificate here
cred = credentials.Certificate(path_to_private_key)
firebase_admin.initialize_app(cred, {
    'storageBucket': 'waterfowltool.appspot.com'
})

store = firestore.client()
bucket = storage.bucket()

#########################################push jpegs to cloud######################################
foldername=os.path.basename(path_to_folder_of_images)

#iterate through images in folder of images
for image_name in os.listdir(path_to_folder_of_images):
    print image_name
    #define folder name and name image will have in the folder here
    blob = bucket.blob(foldername+'/'+image_name)

    #select image from file that will be pushed to the cloud
    outfile=path_to_folder_of_images+'\\'+image_name

    #upload to firebase
    blob.upload_from_filename(outfile)
##################################################################################################                  

################################write json to cloud (no longer needs to be run becuase we are only storing images in firebase and no data)#################################
#point to json here
##with open(path_to_json) as data_file:
##  data = json.load(data_file)
##  for area in data:
##
##    for unit in data[area]:
##
##      for pool in data[area][unit]:
##
##        for wcs in data[area][unit][pool]:
##
##          for gauge in data[area][unit][pool][wcs]: 
##            store.collection(u'Conservation_Areas').document(area).set({u'placeholder':u'placeholder'})
##            store.collection(u'Conservation_Areas').document(area).collection(u'Units').document(unit).set({u'placeholder':u'placeholder'})
##            store.collection(u'Conservation_Areas').document(area).collection(u'Units').document(unit).collection(u'Pools').document(pool).set({u'placeholder':u'placeholder'})
##            store.collection(u'Conservation_Areas').document(area).collection(u'Units').document(unit).collection(u'Pools').document(pool).collection(u'WCS').document(wcs).set({u'placeholder':u'placeholder'})
##            store.collection(u'Conservation_Areas').document(area).collection(u'Units').document(unit).collection(u'Pools').document(pool).collection(u'WCS').document(wcs).collection(u'Gauges').document(gauge).set({u'placeholder':u'placeholder'})
##
##            for stat in data[area][unit][pool][wcs][gauge]:
##              print stat
##
##              if (stat=='Image_Name'):
##                store.collection(u'Conservation_Areas').document(area).collection(u'Units').document(unit).collection(u'Pools').document(pool).collection(u'WCS').document(wcs).collection(u'Gauges').document(gauge).collection(u'Stats').document(stat).set({u'Image_Name':data[area][unit][pool][wcs][gauge][stat]})
##
##              if (stat=="Flooded_Habitat_By_Acres" ):
##                store.collection(u'Conservation_Areas').document(area).collection(u'Units').document(unit).collection(u'Pools').document(pool).collection(u'WCS').document(wcs).collection(u'Gauges').document(gauge).collection(u'Stats').document(stat).set(data[area][unit][pool][wcs][gauge][stat])
##
##              if (stat=="Flooded_Crop_Stats_By_Acre"):
##
##                for crop in data[area][unit][pool][wcs][gauge][stat]:
##  
##                  store.collection(u'Conservation_Areas').document(area).collection(u'Units').document(unit).collection(u'Pools').document(pool).collection(u'WCS').document(wcs).collection(u'Gauges').document(gauge).collection(u'Stats').document(stat).collection(u'Crops').document(crop).set(data[area][unit][pool][wcs][gauge][stat][crop])

################################################################################################
