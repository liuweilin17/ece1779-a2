from flask import render_template, request, flash, redirect, url_for, session
from flaskr import app
from flaskr import db
from flaskr import s3
from flaskr import utils
from werkzeug.utils import secure_filename
import os
import hashlib
from flaskr.models import Image, User
from flaskr.openCV import face_detect_cv3
from flaskr.pillow import thumbs
import traceback
from flaskr.login import hash_password

@app.route('/upload')
def upload():
    utils.record_requests(app.config['INSTANCE_ID'])
    user = session['user'] if 'user' in session else None

    if not user:
        return redirect(url_for('login'))
    else:
        return render_template('upload.html')

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def save_file(file, userid=''):
    try:
        filename = secure_filename(file.filename)
        filetype = filename.rsplit('.', 1)[1].lower()
        img_key = hashlib.md5(file.read()).hexdigest()
        filename = img_key + '.' + filetype
        if not userid:
            userid=session['user']['userid']
        image = Image.query.filter_by(path=filename, userid=userid).first()

        if not image: # file not exists for userid
            print("new image")
            # set the cursor to the beginning of the file
            file.seek(0)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

            # create thumbnail
            size = [200, 200]
            thumb = thumbs.Thumbs(size)
            thumb.run(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            print("create thumbnail of raw")

            # face detect
            ft = face_detect_cv3.FaceDetect()
            faceNum, output_img = ft.run(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            print("face detection")
            if output_img:
                thumb.run(output_img)
                print("create thumbnail of faces")

            # upload four image to S3
            raw = filename
            name, type = os.path.splitext(raw)
            raw_thumb = name + '_thumb' + type
            faces = name + '_faces' + type
            faces_thumb = name + '_faces_thumb' + type

            s3.upload_file(os.path.join(app.config['UPLOAD_FOLDER'], raw), app.config['BUCKET_NAME'], raw)
            s3.upload_file(os.path.join(app.config['UPLOAD_FOLDER'], raw_thumb), app.config['BUCKET_NAME'], raw_thumb)
            s3.upload_file(os.path.join(app.config['UPLOAD_FOLDER'], faces), app.config['BUCKET_NAME'], faces)
            s3.upload_file(os.path.join(app.config['UPLOAD_FOLDER'], faces_thumb), app.config['BUCKET_NAME'], faces_thumb)

            # empty UPLOAD_FOLDER
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], raw))
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], raw_thumb))
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], faces))
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], faces_thumb))

            # insert new image path
            image1 = Image(path=filename, userid=userid)
            db.session.add(image1)
            db.session.commit()
            print('insert new image path into database')

        return img_key + '_faces.' + filetype

    except Exception as e:
        print(e)
        traceback.print_tb(e.__traceback__)
        return ''

def check_image_request(request):
    valid, msg, file = True, '', None
    if request.method == 'POST':
        if 'customFile' in request.files:
            file = request.files['customFile']
            if file.filename != '':
                if not file:
                    valid = False
                    msg = 'file is empty'
                elif not allowed_file(file.filename):
                    valid = False
                    msg = 'invalid file type'
                else:
                    valid = True
                    msg = 'success'
            else:
                valid = False
                msg = 'no selected file'
        else:
            valid = False
            msg = 'no file part'
    else:
        valid = False
        msg = 'invalid method'

    return [valid, msg, file]

@app.route('/uploadImage', methods=['GET', 'POST'])
def upload_image():
    utils.record_requests(app.config['INSTANCE_ID'])
    try:
        valid, msg, file = check_image_request(request)
        print(msg)
        output_img = ''
        if valid:
            output_img = save_file(file)
        return output_img

    except Exception as e:
        # print(e)
        traceback.print_tb(e.__traceback__)
        return ''

@app.route('/api/upload', methods=['POST'])
def upload_api():
    utils.record_requests(app.config['INSTANCE_ID'])
    try:
        if request.method != 'POST':
            return 'invalid request method'

        # check user
        valid = True
        username = request.values['username']
        password = request.values['password']

        user = User.query.filter_by(username=username).first()
        if user:
            password_hash = hash_password(user.salt, password)
            user = User.query.filter_by(username=username, password_hash=password_hash).first()
            if not user:
                valid = False
                message = "Username or Password does not exist"
        else:
            valid = False
            message = "Username or Password does not exist"

        if valid:
            if 'file' in request.files:
                file = request.files['file']
                filename = secure_filename(file.filename)
                if filename != '':
                    if not file:
                        message = 'file is empty'
                    elif not allowed_file(filename):
                        print(filename)
                        message = 'invalid file type'
                    else:
                        # updload file
                        save_file(file, user.userid)
                        message = file.filename + ' upload success'
                else:
                    message = 'no selected file'
            else:
                message = 'no name [file] in form data'

        return message

    except Exception as e:
        print(e)
        traceback.print_tb(e.__traceback__)
        return 'Upload Fail'