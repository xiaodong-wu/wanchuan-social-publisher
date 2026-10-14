"""Create a small source-backed social topic plan, without article SEO requirements."""
import re


def build_content_plan(product):
    facts = product['facts']['declared']
    source = facts.get('product_name') or product['title'].split('|')[0]
    phrase = re.sub(r'\bVantrend\s+Beauty\b|\bVC-[A-Z0-9-]+\b', '', source, flags=re.I)
    phrase = re.sub(r'\s+', ' ', phrase).strip(' -|')
    if not 2 <= len(phrase.split()) <= 12:
        raise ValueError('Product has no natural, source-backed social topic')
    return {
        'core_keyword': phrase, 'source_text': source,
        'source_url': product['canonical_url'],
        'related_topics': product.get('use_cases', [])[:4],
        'buyer_intent': 'product evaluation and sourcing inquiry',
        'instructions': 'Use natural social copy; related topics are optional. Trace all claims to product evidence.',
    }
