from pprint import pprint
import requests
import json
import markdown

api = 'http://127.0.0.1:5000/api'

text = 'BFT induces the antiapoptotic protein cIAP2 and the polyamine catalyst spermine oxidase (SMO), which triggers ROS production, DNA damage, and cell proliferation.'

data = {
    'text': text,
    'named_entities': True,
}

r = requests.post(api, json=data)

response = r.json()

with open('response.json', 'w', encoding='utf-8') as f:
    json.dump(response, f, ensure_ascii=False, indent=2)

with open('tables.html', 'w', encoding='utf-8') as f:
    html = ''
    html += '<link rel=\"stylesheet\" type=\"text/css\" href=\"https://stackpath.bootstrapcdn.com/bootstrap/4.1.3/css/bootstrap.min.css\">\n'
    for key, values in response['markdown_tables'].items():
        md = values['markdown']
        table = markdown.markdown(md, extensions=['markdown.extensions.tables'])
        html += '<h3>{}</h3>'.format(values['title'])
        html += table
        html += '<br /><br />'
    f.write(html)