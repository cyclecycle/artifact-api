import os
import sys
from flask import Flask, jsonify, request, Blueprint, render_template, make_response
from flask_cors import CORS, cross_origin
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
CWD = os.path.dirname(os.path.realpath(__file__))
sys.path.append(CWD)
import json
import re
from pprint import pprint
from badoda import Badoda
from lance import Lance
# import visualise_spacy_tree
import annotate


client_bp = Blueprint(
    'client_app', __name__,
    url_prefix='',
    static_url_path='',
    static_folder='../luscient-website/dist',
    template_folder='../luscient-website/dist',
)


@client_bp.route('/')
def index():
    return render_template('index.html')


@client_bp.route('/artifact')
def artifact():
    return render_template('index.html')


# configuration
DEBUG = True

# instantiate the app
app = Flask(__name__, static_url_path='', static_folder='../luscient-website/dist',)
app.config.from_object(__name__)
# app.register_blueprint(api_bp)
app.register_blueprint(client_bp)

# enable CORS
CORS(app)

limiter = Limiter(
    app,
    key_func=get_remote_address,
)


@app.route('/api', methods=['GET', 'POST'])
@cross_origin()
@limiter.limit('50 per day')
def fact_extraction():
    text = None
    if request.method == 'POST':
        text = request.get_json().get('text')
        get_named_entities = request.get_json().get('named_entities', False)
        detect_valence = request.get_json().get('detect_valence', False)
        get_func_rels = request.get_json().get('get_func_rels', False)
        sigma_graph = request.get_json().get('sigma_graph',  True)
        pmid = request.get_json().get('pmid', False)
        coref_clusters = request.get_json().get('coref_clustsers', False)
        resolve_corefs = request.get_json().get('resolve_corefs', False)
        nlp_json_output = request.get_json().get('nlp_json_output', False)
        disable_length_constraints = request.get_json().get('disable_length_constraints', False)
        tree_plots = request.get_json().get('tree_plots', False)
        # resolve_acros = request.get_json().get('resolve_acros', False)
        resolve_acros = False
        markdown_tables = request.get_json().get('markdown_tables', False)
    if request.method == 'GET':
        text = request.args.get('text')
    if not text:
        return jsonify({'error': 'No value for \'text\' given.'})
    text = str(text)
    if not disable_length_constraints:
        char_limit = 800
        if len(text) > char_limit:
            return jsonify({'error': 'That text is too long ({0} characters). Must be less than {1}.' .format(len(text), char_limit)})
    try:
        preprocess_settings = {
            'resolve_acros': resolve_acros,
            'resolve_corefs': resolve_corefs,
        }
        if coref_clusters:
            preprocess_settings['coref_clusters'] = True
        badoda = Badoda(text, preprocess_settings=preprocess_settings, verbose=False)
        # ent_phrase_rels = sorted(ent_phrase_rels, key=lambda x: (x['subj']['text'], x['pred']['text'], x['obj']['text']))
        response = {
            'original_text': text,
            'preprocessed_text': badoda.preprocessed_text,
        }

        badoda.get_parse_trees()

        if nlp_json_output:
            response['sentences'] = badoda.json_sents
            response['parse_trees'] = {'original': badoda.json_trees}
            if tree_plots:
                for i, tree in enumerate(badoda.trees):
                    plot = visualise_spacy_tree.plot(tree)
                    response['parse_trees']['original'][i]['tree_plot_png'] = plot.decode(encoding='ISO-8859-1')

        badoda.chunk_trees()

        if nlp_json_output:
            response['parse_trees']['chunked'] = badoda.json_trees
            if tree_plots:
                for i, tree in enumerate(badoda.trees):
                    plot = visualise_spacy_tree.plot(tree)
                    response['parse_trees']['chunked'][i]['tree_plot_png'] = plot.decode(encoding='ISO-8859-1')

        badoda.get_relationships()
        ent_phrase_rels = badoda.relationships

        if markdown_tables:
            response['markdown_tables'] = {}
        if get_named_entities:
            named_ents = annotate.get_becas_annotations(badoda.preprocessed_text)
            response['named_ents'] = named_ents
            annotate.annotate_triples_with_ents(ent_phrase_rels, named_ents)
            # pprint(ent_phrase_rels)
        if detect_valence or get_func_rels:
            lance = Lance(badoda)
            func_rels = lance.func_rels
            response['functional_relationships'] = func_rels
            response['valence_annotations'] = lance.valence_annotations
            if markdown_tables:
                ent_func_rels_md = func_rels_markdown_table(func_rels['entity_level'])
                phrase_func_rels_md = func_rels_markdown_table(func_rels['phrase_level'])
                response['markdown_tables'] = {
                    'entity_level_func_rels': {
                        'markdown': ent_func_rels_md,
                        'title': 'Functional Relationships (entity level)'
                    },
                    'phrase_level_func_rels': {
                        'markdown': phrase_func_rels_md,
                        'title': 'Functional Relationships (phrase level)'
                    },
                }
        response['entity_phrase_relationships'] = ent_phrase_rels
        if markdown_tables:
            epr_md = triples_to_markdown_table(ent_phrase_rels)
            response['markdown_tables']['entity_phrase_relationships'] = {
                        'markdown': epr_md,
                        'title': 'Entity Phrase Relationships'
                    }
        if sigma_graph:
            graph = generate_sigma_graph(ent_phrase_rels)
            response['graph_data'] = graph
        # if coref_clusters:
            # add coref clusters json to output

            # Create 
            # token_i_to_coref_cluster = {}
            # for cluster in self.doc._.coref_clusters:
            #     for span in cluster.mentions:
            #         for token in span:
            #             token_i_to_coref_cluster[token.i] = cluster.main.i
            # pprint(token_i_to_coref_cluster)
        return jsonify(response)
    except Exception as e:
        raise e
        return jsonify({'error': 'An error occurred processing that text. Please try something else.'})


def triples_to_markdown_table(triples):
    md = '| Entity phrase left | Relation | Entity phrase right | Voice |\n|---|---|---|---|'
    for triple in triples:
        md += '\n| {0} | {1} | {2} | {3} |'.format(
            triple['subj']['text'],
            triple['pred']['text'],
            triple['obj']['text'],
            triple['voice'],
        )
    # print(md)
    return md


def func_rels_markdown_table(func_rels):

    def valence_to_arrow(valence):
        if valence == 'UP':
            return '&uarr;'
        if valence == 'DOWN':
            return '&darr;'

    md = '| Antecedent | Consequent |\n|---|---|\n'
    for item in func_rels:
        md += '| {ant_arrow} {ant_text} | {sub_arrow} {sub_text} |\n'.format(
            ant_arrow=valence_to_arrow(item['antecedent']['valence']),
            ant_text=item['antecedent']['text'],
            sub_arrow=valence_to_arrow(item['consequent']['valence']),
            sub_text=item['consequent']['text'],
        )
    return md


def generate_sigma_graph(triple_data, **kwargs):
    nodes = []
    edges = []
    ent_id2degree = {}
    for i, item in enumerate(triple_data):
        for component in ['subj', 'obj']:
            ent_id = item[component]['ent_id']
            if not ent_id in ent_id2degree:
                nodes.append({
                    'id': ent_id,
                    'label': item[component]['text']
                })
                ent_id2degree[ent_id] = 1
            else:
                ent_id2degree[ent_id] += 1
        edges.append({
            'id': 'e' + str(i),
            'label': item['pred']['text'],
            'source': item['subj']['ent_id'],
            'target': item['obj']['ent_id'],
        })
    for node in nodes:
        node['size'] = ent_id2degree[node['id']]
    graph = {'nodes': nodes, 'edges': edges}
    # pprint(graph)
    return graph


@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({
        'error': 'Request limit exceeded. For heavier usage, please contact us at luscient.tech@gmail.com'
    })


if __name__ == '__main__':
    app.run()
