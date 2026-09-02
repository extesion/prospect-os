import urllib.request
import json
import base64

# 1. Login
login_data = json.dumps({'email': 'carlos@prospector.com', 'password': '123'}).encode('utf-8')
login_req = urllib.request.Request(
    'https://prospect-os-seven.vercel.app/api/auth/login',
    data=login_data,
    headers={'Content-Type': 'application/json'},
    method='POST'
)
login_res = urllib.request.urlopen(login_req)
token = json.loads(login_res.read().decode('utf-8'))['access_token']
print("Authenticated successfully, token obtained.")

# 2. Upload Avatar
boundary = "----WebKitFormBoundaryTest123"
# 1x1 valid transparent PNG
png_bytes = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")

body = (
    f"--{boundary}\r\n"
    f"Content-Disposition: form-data; name=\"file\"; filename=\"avatar.png\"\r\n"
    f"Content-Type: image/png\r\n\r\n"
).encode('utf-8') + png_bytes + f"\r\n--{boundary}--\r\n".encode('utf-8')

upload_req = urllib.request.Request(
    'https://prospect-os-seven.vercel.app/api/profiles/upload/avatar',
    data=body,
    headers={
        'Content-Type': f'multipart/form-data; boundary={boundary}',
        'Authorization': f'Bearer {token}'
    },
    method='POST'
)

upload_res = urllib.request.urlopen(upload_req)
print("Avatar Upload Status:", upload_res.status)
data = json.loads(upload_res.read().decode('utf-8'))
print("Avatar URL start:", data.get("url", "")[:50])

# 3. Upload Banner
banner_req = urllib.request.Request(
    'https://prospect-os-seven.vercel.app/api/profiles/upload/banner',
    data=body,
    headers={
        'Content-Type': f'multipart/form-data; boundary={boundary}',
        'Authorization': f'Bearer {token}'
    },
    method='POST'
)

banner_res = urllib.request.urlopen(banner_req)
print("Banner Upload Status:", banner_res.status)
b_data = json.loads(banner_res.read().decode('utf-8'))
print("Banner URL start:", b_data.get("url", "")[:50])
