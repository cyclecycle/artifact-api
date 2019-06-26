import re
import becas
from pprint import pprint

becas.email = 'luscient.tech@gmail.com'


def annotate_triples_with_ents(triple_data, named_ents):
    for annot in named_ents:
        # Sort refs to ensure consistent order across API calls. Important because at present the first ref is used to associate the component with a concept id.
        annot['refs'] = sorted(annot['refs'], key=lambda x: x['id'])
    for triple in triple_data:
        if not all(component in triple for component in ['subj', 'pred', 'obj']):
            continue
        for component in {'subj', 'pred', 'obj'}:
            ents = []
            spans = [token['span'] for token in triple[component]['tokens']]
            contig_spans = join_contiguous_spans(spans)
            for span in contig_spans:
                start = span[0]
                end = span[1]
                for annot in named_ents:
                    if annot['start'] >= start and annot['end'] <= end:
                        if annot not in ents:
                            ents.append(annot)
            ents = assign_precedence_to_ents(ents)
            triple[component]['named_ents'] = ents
    return triple_data


def get_becas_annotations(text):
    annots = becas.annotate_text(text)
    annots = [item.split('|') for item in annots['entities']]
    d = []
    for item in annots:
        term, refs, start = item[0], item[1], int(item[2])
        parsed_refs = []
        for ref in refs.split(';'):
            ref = ref.split(':')
            parsed_refs.append({
                'source': ref[0],
                'id': ref[1],
                'sub_id':  ref[2],
                'class': ref[3],
            })
        d.append({
            'term': term,
            'refs': parsed_refs,
            'start': start,
            'end': start + len(term)
        })
    d = sorted(d, key=lambda x: x['start'])
    return d


def assign_precedence_to_ents(ents):
    '''Features may include:
        position relative to prep,
        class of annotation,
        tfidf,
        specifitiy or level of the term in an ontology
        number of sources recognising it (less implies more specific)
    '''
    # If contains 'of' and ent after, take that
    # If 'in' and ent before, take that
    # Becas ent priority order:
    becas_class_priority_order = [
        'PRGE',
        'ENZY',
        'MRNA',
        'CHED',
        'DISO',
        'SPEC',
        'PATH',
        'ANAT',
        'PROC',
        'FUNC',
        'COMP',
    ]
    source_priority_order = [
        'UNIPROT',
        'CHEBI',
        'UMLS',
        'NCBI',
        'GO',
    ]

    def get_precedence(ent):
        class_rank = len(becas_class_priority_order)
        source_rank = len(source_priority_order)
        for ref in ent['refs']:
            for i, cl in enumerate(becas_class_priority_order):
                if ref['class'] == cl:
                    if i < class_rank:
                        class_rank = i
            for i, cl in enumerate(source_priority_order):
                if ref['source'] == cl:
                    if i < source_rank:
                        source_rank = i
        return (
            class_rank,
            source_rank,
            ent['start'],
            len(ent['term'])
        )

    ents = sorted(ents, key=lambda x: get_precedence(x))
    for i, ent in enumerate(ents):
        ent['precedence'] = i + 1
    return ents


def annotate_pubtator_entities(triples, annots):
    annots = {
        "0": {
          "pubtator_class": "gene",
          "pubtator_mapped_class": "biomolecule",
          "pubtator_offset": 67.0,
          "term": "Sotrastaurin"
        },
        "1": {
          "pubtator_class": "gene",
          "pubtator_mapped_class": "biomolecule",
          "pubtator_offset": 24.0,
          "term": "pAkt1"
        },
    }
    for triple in triples:
        for component in {'subj', 'pred', 'obj'}:
            ents = []
            text = triple[component]['text']
            for annot in annots.values():
                term = annot['term']
                found = re.finditer(r'{}'.format(term), text)
                for match in found:
                    result = {
                        'term': term,
                        'start': match.start() + 1,
                        'end': match.end() - 1,
                        'provenance': 'pubtator'
                    }
                    ents.append(result)
            try:
                triple[component]['named_ents'] =+ ents
            except:
                triple[component]['named_ents'] = ents
    return triples


def get_annotations(text, dbpedia=False, pubtator=False, pmid=False):
    annots = {}
    if dbpedia:
        annotator = Annotator()
        df = annotator.dbpedia_annotations(text)
        df['term'] = df.index
        df.reset_index(inplace=True, drop=True)
        dict_ = df.transpose().to_dict()
        annots['dbpedia'] = dict_
    if pubtator:
        if not pmid:
            return {}
        annotator = Annotator()
        df = annotator.pubtator_annotations(pmid)
        df['term'] = df.index
        df.reset_index(inplace=True, drop=True)
        dict_ = df.transpose().to_dict()
        annots['dbpedia'] = dict_
    return annots


def join_contiguous_spans(spans):
    if len(spans) <= 1:
        return spans
    contig = []
    n_spans = len(spans)
    spans_subsumed = []
    for i, span in enumerate(spans):
        next_i = i + 1
        if next_i >= n_spans:
            continue
        if i in spans_subsumed:
            continue
        next_span = spans[next_i]
        if next_span[0] == span[1] + 1:
            contig_span = (span[0], next_span[1])
            contig.append(contig_span)
            spans_subsumed.append(i)
            continue
        contig.append(span)
    return contig
