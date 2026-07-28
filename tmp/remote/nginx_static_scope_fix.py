from pathlib import Path

p = Path('/etc/nginx/sites-enabled/oa-proxy.conf')
s = p.read_text()
old = '''    location ^~ /static/ {
        proxy_pass http://127.0.0.1:5666/static/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

'''
new = '''    location ^~ /static/imgs/oa-template-icons/ {
        proxy_pass http://127.0.0.1:5666/static/imgs/oa-template-icons/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

'''
if old not in s:
    raise SystemExit('static location not found')
p.write_text(s.replace(old, new))
