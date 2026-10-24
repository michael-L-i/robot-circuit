"""Exercise real local vision with an intentionally blank image (not an accuracy test)."""
import base64
import io
import json
import urllib.request
from PIL import Image

def main():
    buf = io.BytesIO()
    Image.new('RGB', (320, 240), 'white').save(buf, format='JPEG')
    body = json.dumps({'image':base64.b64encode(buf.getvalue()).decode()}).encode()
    req = urllib.request.Request('http://127.0.0.1:8000/api/analyze', data=body, headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=300) as response:
        result = json.load(response)
    print(json.dumps(result, indent=2))
    assert result['requires_review']
    assert all(value is None for value in result['pins'].values()), 'Blank image should not produce pin labels'
    assert 'raw_output' not in result, 'Model output must be valid structured observations'


if __name__ == "__main__":
    main()
