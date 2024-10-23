import os
import cv2
import numpy as np
import random
import base64
import requests
import json
import time
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional

app = FastAPI()

MAX_SEED = 999999

def process_image(file: UploadFile):
    # Convert uploaded image file to numpy array
    image_bytes = file.file.read()
    nparr = np.fromstring(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    return img

def encode_image_to_base64(image):
    # Encode image as base64
    _, buffer = cv2.imencode('.jpg', image)
    encoded_image = base64.b64encode(buffer).decode('utf-8')
    return encoded_image

@app.post("/tryon")
async def tryon(
    person_img: UploadFile = File(...), 
    garment_img: UploadFile = File(...), 
    seed: Optional[int] = Form(0), 
    randomize_seed: Optional[bool] = Form(False)
):
    try:
        # Process images
        person_img_np = process_image(person_img)
        garment_img_np = process_image(garment_img)

        if randomize_seed:
            seed = random.randint(0, MAX_SEED)

        # Encode images to base64
        encoded_person_img = encode_image_to_base64(person_img_np)
        encoded_garment_img = encode_image_to_base64(garment_img_np)

        # Set up external API request
        url = "http://" + os.environ['tryon_url'] + "Submit"
        token = os.environ['token']
        cookie = os.environ['Cookie']
        referer = os.environ['referer']
        headers = {'Content-Type': 'application/json', 'token': token, 'Cookie': cookie, 'referer': referer}
        
        data = {
            "clothImage": encoded_garment_img,
            "humanImage": encoded_person_img,
            "seed": seed
        }

        post_start_time = time.time()
        
        # Make the POST request
        response = requests.post(url, headers=headers, data=json.dumps(data), timeout=50)
        if response.status_code == 200:
            result = response.json()['result']
            status = result['status']
            if status == "success":
                uuid = result['result']
            else:
                return JSONResponse(content={"message": "Error in external API"}, status_code=500)
        else:
            return JSONResponse(content={"message": "Failed to call external API"}, status_code=500)

        post_end_time = time.time()

        # Poll for the result
        get_start_time = time.time()
        time.sleep(9)
        Max_Retry = 12
        result_img = None
        info = ""
        err_log = ""
        
        for _ in range(Max_Retry):
            try:
                query_url = f"http://{os.environ['tryon_url']}Query?taskId={uuid}"
                response = requests.get(query_url, headers=headers, timeout=20)
                if response.status_code == 200:
                    result = response.json()['result']
                    status = result['status']
                    if status == "success":
                        result = base64.b64decode(result['result'])
                        result_np = np.frombuffer(result, np.uint8)
                        result_img = cv2.imdecode(result_np, cv2.IMREAD_UNCHANGED)
                        result_img = cv2.cvtColor(result_img, cv2.COLOR_RGB2BGR)
                        info = "Success"
                        break
                    elif status == "error":
                        err_log = "Error status returned"
                        info = "Error"
                        break
                else:
                    err_log = "API URL Error"
                    info = "API Error"
                    break
            except requests.exceptions.ReadTimeout:
                err_log = "HTTP Timeout"
                info = "Timeout, try again later"
            except Exception as err:
                err_log = f"Exception: {err}"
            time.sleep(1)
        
        get_end_time = time.time()

        if not info == "Success":
            raise HTTPException(status_code=500, detail=f"Error: {err_log}")

        print(f"Post time: {post_end_time-post_start_time}, Get time: {get_end_time-get_start_time}")

        # Return result image as base64 encoded string
        _, img_buffer = cv2.imencode('.jpg', result_img)
        encoded_result_img = base64.b64encode(img_buffer).decode('utf-8')

        return {
            "image": encoded_result_img,
            "seed": seed,
            "info": info
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
