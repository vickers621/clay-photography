#!/usr/bin/env python3
"""Build img/ derivatives + data.json for clay.photography from photos/."""
import json, os, re, shutil, subprocess, math
from PIL import Image, ImageOps

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC  = os.path.join(ROOT, 'photos')
FULL = os.path.join(ROOT, 'img', 'full')
THUMB= os.path.join(ROOT, 'img', 'thumb')
FULL_EDGE, THUMB_EDGE = 2400, 1000

GROUPS = [
    ('water',  'Water & Coast',        [2,11,13,14,15,18,27,28,30,32,35,39,41,43]),
    ('cities', 'Cities & Architecture',[6,7,8,10,12,16,19,21,25,29,31,33,36]),
    ('land',   'Land & Sky',           [1,4,5,17,22,23,24,26,34,37,38,40]),
    ('above',  'From Above',           [42,44,45,46,47]),
    ('people', 'People',               [0,3,9,20]),
]

def slugify(fn):
    return re.sub(r'[^a-z0-9]+', '-', os.path.splitext(fn)[0].lower()).strip('-')

def exif_all():
    pretty = json.loads(subprocess.run(
        ['exiftool','-json','-g0:1','-api','largefilesupport=1', SRC],
        capture_output=True, text=True).stdout or '[]')
    numeric = json.loads(subprocess.run(
        ['exiftool','-json','-n','-GPSLatitude','-GPSLongitude','-GPSAltitude',
         '-GPSImgDirection','-ExposureTime','-FNumber','-FocalLength', SRC],
        capture_output=True, text=True).stdout or '[]')
    key = lambda d: os.path.basename(d['SourceFile'])
    return {key(d): d for d in pretty}, {key(d): d for d in numeric}

GPS_COARSE = 2          # decimal places kept for published coordinates (~1.1 km)

# Positional tags are removed from the raw dump outright: exiftool renders them
# as DMS ("38 deg 38' 22.35\""), which stays house-precise under any decimal
# rounding. The coarse pair in `gps` is the only location the site publishes.
GPS_DROP = {'GPSLatitude', 'GPSLongitude', 'GPSPosition', 'GPSCoordinates',
            'GPSHPositioningError', 'GPSDateTime', 'GPSTimeStamp', 'GPSDateStamp',
            'GPSLatitudeRef', 'GPSLongitudeRef'}
GPS_ROUND = {'GPSAltitude': 0, 'GPSImgDirection': 1, 'GPSDestBearing': 1, 'GPSSpeed': 1}

def flatten(rec):
    """Group -> {tag: value} for every EXIF group, skipping noise.

    Coordinates are deliberately coarsened here as well as in the summary, so
    the published raw dump can never be more precise than the headline figure.
    """
    skip_groups = {'ExifTool','ICC_Profile:ICC-header','Photoshop'}
    skip_tags = {'Directory','FileAccessDate','FileInodeChangeDate','FilePermissions',
                 'SourceFile','ThumbnailImage','PreviewImage','IPTCDigest',
                 'CurrentIPTCDigest','RedTRC','GreenTRC','BlueTRC','MPImage'}
    out = {}
    for g, v in rec.items():
        if g in skip_groups or not isinstance(v, dict):
            continue
        clean = {k: val for k, val in v.items()
                 if k not in skip_tags and not isinstance(val, (dict, list))
                 and str(val).strip() != '' and len(str(val)) < 300}
        for k in list(clean):
            if k in GPS_DROP:
                del clean[k]
            elif k in GPS_ROUND:
                m = re.match(r'\s*(-?\d+(?:\.\d+)?)(.*)$', str(clean[k]))
                if m:
                    num = round(float(m.group(1)), GPS_ROUND[k])
                    clean[k] = '%s%s' % (int(num) if GPS_ROUND[k] == 0 else num, m.group(2))
        if clean:
            out[g.replace('File:System','File')] = clean
    return out

def summary(p, n):
    """Curated headline facts."""
    e  = p.get('EXIF:ExifIFD', {}); i0 = p.get('EXIF:IFD0', {})
    c  = p.get('Composite', {});    f  = p.get('File', {}); fs = p.get('File:System', {})
    cam = ' '.join(x for x in [i0.get('Make'), i0.get('Model')] if x)
    if i0.get('Make') and i0.get('Model','').startswith(i0['Make']):
        cam = i0['Model']
    rows = [
        ('Camera',        cam),
        ('Lens',          e.get('LensModel') or e.get('LensInfo')),
        ('Focal length',  e.get('FocalLength')),
        ('35mm equiv.',   e.get('FocalLengthIn35mmFormat')),
        ('Aperture',      c.get('Aperture') and 'f/%s' % c['Aperture']),
        ('Shutter',       c.get('ShutterSpeed') and '%s sec' % c['ShutterSpeed']),
        ('ISO',           e.get('ISO')),
        ('Exposure bias', e.get('ExposureCompensation')),
        ('Exposure mode', e.get('ExposureProgram') or e.get('ExposureMode')),
        ('Metering',      e.get('MeteringMode')),
        ('White balance', e.get('WhiteBalance')),
        ('Flash',         e.get('Flash')),
        ('Field of view', c.get('FOV')),
        ('Light value',   c.get('LightValue') and round(float(c['LightValue']), 1)),
        ('Taken',         e.get('DateTimeOriginal')),
        ('Time zone',     e.get('OffsetTimeOriginal')),
        ('Software',      i0.get('Software')),
        ('Dimensions',    c.get('ImageSize')),
        ('Megapixels',    c.get('Megapixels')),
        ('File',          f.get('FileType')),
        ('File size',     fs.get('FileSize')),
        ('Colour profile',p.get('ICC_Profile', {}).get('ProfileDescription')),
    ]
    return [{'k': k, 'v': str(v)} for k, v in rows if v not in (None, '', 'undef')]

def main():
    for d in (FULL, THUMB):
        os.makedirs(d, exist_ok=True)
    files = sorted(f for f in os.listdir(SRC) if not f.startswith('.'))
    pretty, numeric = exif_all()
    photos = {}

    for idx, fn in enumerate(files):
        slug = slugify(fn)
        p, n = pretty.get(fn, {}), numeric.get(fn, {})
        src  = os.path.join(SRC, fn)
        animated = fn.lower().endswith('.gif')

        im = ImageOps.exif_transpose(Image.open(src))
        w, h = im.size

        if animated:                       # keep the loop intact
            full_name = slug + '.gif'
            shutil.copyfile(src, os.path.join(FULL, full_name))
            flat = im.convert('RGB')
        else:
            full_name = slug + '.jpg'
            flat = im.convert('RGB')
            out = flat.copy(); out.thumbnail((FULL_EDGE, FULL_EDGE), Image.LANCZOS)
            out.save(os.path.join(FULL, full_name), 'JPEG',
                     quality=84, optimize=True, progressive=True)

        th = flat.copy(); th.thumbnail((THUMB_EDGE, THUMB_EDGE), Image.LANCZOS)
        th.save(os.path.join(THUMB, slug + '.jpg'), 'JPEG',
                quality=76, optimize=True, progressive=True)

        gps = None
        if 'GPSLatitude' in n and 'GPSLongitude' in n:
            gps = {'lat': round(n['GPSLatitude'], GPS_COARSE),
                   'lon': round(n['GPSLongitude'], GPS_COARSE), 'approx': True}
            if 'GPSAltitude' in n:      gps['alt'] = round(n['GPSAltitude'])
            if 'GPSImgDirection' in n:  gps['dir'] = round(n['GPSImgDirection'], 1)

        photos[idx] = {
            'id': slug, 'file': fn,
            'thumb': 'img/thumb/%s.jpg' % slug,
            'full': 'img/full/%s' % full_name,
            'w': w, 'h': h, 'animated': animated,
            'taken': (p.get('EXIF:ExifIFD', {}).get('DateTimeOriginal')
                      or p.get('File:System', {}).get('FileModifyDate', ''))[:10].replace(':', '-'),
            'gps': gps,
            'summary': summary(p, n),
            'raw': flatten(p),
        }
        print('%2d/%d  %s  %dx%d' % (idx + 1, len(files), slug, w, h))

    data = {'groups': [{'id': gid, 'title': title,
                        'photos': [photos[i] for i in idxs if i in photos]}
                       for gid, title, idxs in GROUPS]}
    with open(os.path.join(ROOT, 'data.json'), 'w') as fh:
        json.dump(data, fh, separators=(',', ':'))
    print('\ndata.json:', sum(len(g['photos']) for g in data['groups']), 'photos in',
          len(data['groups']), 'groups')

if __name__ == '__main__':
    main()
