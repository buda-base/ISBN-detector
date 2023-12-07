import openpecha
import re
import yaml
import io
from tqdm import tqdm
import boto3
import botocore
import gzip
import csv
from pyzbar.pyzbar import decode
from PIL import Image
from pathlib import Path
import os
import hashlib
import json

SESSION = boto3.Session(profile_name='thumbnailgen')
S3 = SESSION.client('s3')

# use yaml.CSafeLoader / if available but don't crash if it isn't
try:
    yaml_loader = yaml.CSafeLoader
except (ImportError, AttributeError):
    yaml_loader = yaml.SafeLoader

try:
    yaml_dumper = yaml.CSafeDumper
except (ImportError, AttributeError):
    yaml_dumper = yaml.SafeDumper

def normalize_isbn(isbn):
    return isbn.upper().replace("-", "").replace(" ", "")

def well_formed(isbn):
    # assumes isbn is normalized
    match = re.search(r'^(\d{9}[0-9X]|\d{12}[0-9X])$', isbn)
    return True if match else False

def valid(isbn):
    # assumes isbn is normalized
    match = re.search(r'^(\d{9})(\d|X)$', isbn)
    if not match:
        return False

    digits = match.group(1)
    check_digit = 10 if match.group(2) == 'X' else int(match.group(2))
    result = sum((i + 1) * int(digit) for i, digit in enumerate(digits))
    return (result % 11) == check_digit

def get_s3_folder_prefix(iiLocalName, igLocalName):
    """
    gives the s3 prefix (~folder) in which the volume will be present.
    inpire from https://github.com/buda-base/buda-iiif-presentation/blob/master/src/main/java/
    io/bdrc/iiif/presentation/ImageInfoListService.java#L73
    Example:
       - iiLocalName=W22084, igLocalName=I0886
       - result = "Works/60/W22084/images/W22084-0886/
    where:
       - 60 is the first two characters of the md5 of the string W22084
       - 0886 is:
          * the image group ID without the initial "I" if the image group ID is in the form I\\d\\d\\d\\d
          * or else the full image group ID (incuding the "I")
    """
    md5 = hashlib.md5(str.encode(iiLocalName))
    two = md5.hexdigest()[:2]

    pre, rest = igLocalName[0], igLocalName[1:]
    if pre == 'I' and rest.isdigit() and len(rest) == 4:
        suffix = rest
    else:
        suffix = igLocalName

    return 'Works/{two}/{RID}/images/{RID}-{suffix}/'.format(two=two, RID=iiLocalName, suffix=suffix)

def gets3blob(s3Key):
    f = io.BytesIO()
    try:
        S3.download_fileobj('archive.tbrc.org', s3Key, f)
        return f
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == '404':
            return None
        else:
            raise

# This has a cache mechanism
def getImageList(iiLocalName, igLocalName, force=False, getmissing=True):
    cachepath = Path("cache/il/"+igLocalName+".json.gz")
    if not force and cachepath.is_file():
        with gzip.open(str(cachepath), 'r') as gzipfile:
            try:
                res = json.loads(gzipfile.read())
                return res
            except:
                tqdm.write("can't read "+str(cachepath))
                pass
    if not getmissing:
        return None
    s3key = get_s3_folder_prefix(iiLocalName, igLocalName)+"dimensions.json"
    blob = gets3blob(s3key)
    if blob is None:
        return None
    blob.seek(0)
    b = blob.read()
    ub = gzip.decompress(b)
    s = ub.decode('utf8')
    data = json.loads(s)
    with gzip.open(str(cachepath), 'w') as gzipfile:
        gzipfile.write(json.dumps(data).encode('utf-8'))
    return data

def getimg(wlname, iglname, fname):
    key = get_s3_folder_prefix(wlname, iglname)+fname
    blob = gets3blob(key)
    return Image.open(blob)

#
# db format
#
# MW:
#   nb_vols_catalog: int
#   catalog_isbn: ""
#   catalog_isbn_valid: boolean
#   Identifiers:
#     1: [ isbns for vol 1 ]
#     2: [ isbns for vol 2 ]
# W:
#   ro: MW
#   I:
#     n: int
#     imgs:
#        fname:
#          - t: EAN13
#            d: 9787800571282
#            r: [l, t, w, h]
#        

def get_w_infos():
    res = {}
    with open('mw-w-ig-vn.csv', newline='') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            mw = row[0]
            w = row[1]
            ig = row[2]
            vn = int(row[3])
            ti = int(row[4])
            if w not in res:
                res[w] = {}
            res[w]["ro"] = mw # reproduction of
            res[w][ig] = {
                "n": vn,
                "ti": ti
            }
    return res

def has_id(db_ig_info):
    # returns True if an id has been found for this ig:
    if "imgs" not in db_ig_info:
        return False
    for fname, detections in db_ig_info["imgs"]:
        if detections:
            return True
    return False

def ordered_imglist(fnames, nb_tip):
    # tip = tbrc intro pages
    # most likely are 10 last then 10 first
    res = []
    l = len(fnames)
    for i in range(1, min(10, l-nb_tip)):
        res.append(fnames[l-i]["filename"])
    for i in range(nb_tip, min(10, l)):
        if fnames[i] not in res:
            res.append(fnames[i]["filename"])
    return res

def get_detections(pil_img):
    info = decode(pil_img)
    if info is None:
        return [], False
    res = []
    found = False
    for d in info:
        data_str = None
        try:
            data_str = d.data.decode('ascii')
        except:
            print("cannot convert to string: "+str(d.data))
        resi = {
            "t": d.type,
            "d": data_str
        }
        if d.type.startswith("EAN"):
            found = True
        if d.rect:
            resi["r"] = ",".join([str(d.rect.left), str(d.rect.top), str(d.rect.width), str(d.rect.height)])
        res.append(resi)
    return res, found


def process_ig(w, ig, ig_info, db_ig_info, re_run_det=False):
    if has_id(db_ig_info):
        return
    flist = getImageList(w, ig)
    if flist is None:
        print("could not get image list for "+w+"-"+ig)
        return
    ordered_flist = ordered_imglist(flist, ig_info["ti"])
    for imgfname in ordered_flist:
        if imgfname in db_ig_info and not re_run_det:
            continue
        img = getimg(w, ig, imgfname)
        dets, found = get_detections(img)
        db_ig_info[imgfname] = dets
        if found:
            break
        

def process_w(wrid, w_info, db_w_info):
    for ig, ig_info in w_info.items():
        if ig == "ro":
            continue
        if ig not in db_w_info:
            db_w_info[ig] = {
                "n": ig_info["n"]
            }
        process_ig(wrid, ig, ig_info, db_w_info[ig])

def main(wrid = None):
    w_infos = get_w_infos()    
    # this currently only generates db.yml
    # create image list cache dir
    cachedir = Path("cache/il/")
    if not cachedir.is_dir():
        os.makedirs(str(cachedir))
    # read db
    db = {}
    if wrid is not None:
        if wrid not in db:
            db[wrid] = {}
        process_w(wrid, w_infos[wrid], db[wrid])
        print(yaml.dump(db[wrid], Dumper=yaml_dumper))
        return
    if Path("db.yml").is_file():
        with open("db.yml", 'r') as stream:
            db = yaml.load(stream, Loader=yaml_loader)
    i = 0
    for w in tqdm(sorted(w_infos)):
        if w not in db:
            db[w] = {}
        process_w(w, w_infos[w], db[w])
        i += 1
        if i>= 1000:
            try:
                with open("db.yml", 'w') as stream:
                    yaml.dump(db, stream, Dumper=yaml_dumper)
                i = 0
            except KeyboardInterrupt:
                # poor man's atomicity
                time.sleep(2)
                raise
    print("writing db.yml")
    if i > 0:
        with open("db.yml", 'w') as stream:
            yaml.dump(db, stream, Dumper=yaml_dumper)

main()
