#!/usr/bin/env python3
"""Offline behavioral checks; never contacts or publishes to external services."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import scrape_product as scrape
from content_plan import build_content_plan
from optimize_image import strip_metadata, compress, validate, create_transport_jpeg
from update_manifest import load_manifest, write_manifest, update_manifest, SHEET_ID, SHEET_URL, IDENTITIES
from validate_campaign import validate_campaign, digest
from validate_completion import expected_row, validate_completion

URL='https://www.vantrendtools.com/vc-21.html'
HTML='''<div class="product_gallery_main"><img src="/hero.webp"></div>
<div class="product_info"><h1>Vantrend Beauty VC-21 Electric Nail Drill</h1>
<p class="product_info_description">VC-21 cordless nail drill for nail salons.</p>
<ul class="product_attributes"><li>Model: <strong>VC-21</strong></li><li>Battery: <strong>550mAh Rechargeable Battery</strong></li></ul></div>
<section class="product_specifications"><table><tr><th>Model</th><td>VC-21</td></tr><tr><th>Battery</th><td>550mAh</td></tr><tr><th>Material</th><td>Aluminum</td></tr><tr><th>Rotation</th><td>Forward and reverse</td></tr></table></section>
<div class="show_item_box7"><p>VC-21 nail filing and gel removal.</p></div>
<section class="product_reviews">Guaranteed medical sterilization</section>'''


def parse(html):
    p=scrape.VantrendHTMLParser();p.raw_html=html;p.feed(html);p.close();return p


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def product(self):
        with patch.object(scrape,'fetch_html',return_value=parse(HTML)):
            return scrape.extract_product(URL)
    def campaign(self, mode='live'):
        product=self.product();plan=build_content_plan(product)
        from io import BytesIO
        b=BytesIO();Image.new('RGB',(1000,1000),'#b27672').save(b,'PNG')
        with patch.object(scrape,'fetch_bytes',return_value=(b.getvalue(),'image/png')):
            run=scrape.create_run(product,self.root,plan,mode)
        path=run/'manifest.json';m=load_manifest(path)
        fb='''💅 Cordless pen design supports convenient nail filing during routine care.
🔋 A rechargeable battery provides a portable power source for the handpiece.
⚙ Forward and reverse rotation offers a practical control option for technicians.
📦 An aluminum body brings a clear material specification to your sourcing review.

Consider this nail drill when evaluating equipment for your nail salon product range. Review the available product information and discuss the configuration your business needs before placing an order.

Contact Vantrend Beauty with your product questions and purchasing requirements.

'''+URL+'\n\n#NailDrill #NailCare #BeautyTools #NailSalon #Manicure #Sourcing #BeautySupply #NailTools'
        li='''Choosing a nail drill for your product range starts with checking the details that affect daily handling and procurement conversations. A clear product specification helps buyers compare options and ask focused questions before ordering.

- Cordless pen design provides a compact format for nail care.
- Rechargeable battery supports portable use of the handpiece.
- Forward and reverse rotation provides a useful control option.
- Aluminum construction gives buyers a documented material reference.

The VC-21 is presented for nail salons, with nail filing and gel removal described in its product information. These details give purchasing teams a starting point for evaluating whether the product matches their intended assortment. Review the stated specifications alongside your own requirements, and confirm the final configuration directly with the supplier. Product selection should account for the intended users and working environment as well as the documented features.

Contact Vantrend Beauty to discuss your sourcing questions, request further product information, and confirm the details needed for your purchasing review.

'''+URL+'\n\n#NailDrill #BeautyTools #Sourcing'
        Path(m['artifacts']['facebook_copy']).write_text(fb)
        Path(m['artifacts']['linkedin_copy']).write_text(li)
        im=Image.new('RGB',(1000,1000),'#c39988');enc,final,_=compress(strip_metadata(im),750*1024,(960,960))
        Path(m['artifacts']['social_image']).write_bytes(enc)
        create_transport_jpeg(final,Path(m['artifacts']['social_upload']))
        review={'product_url':URL,'source_review':'passed','copy_review':'passed','image_review':'passed',
                'claims':[{'claim':x,'quote':x} for x in ['VC-21','550mAh','Aluminum','Forward and reverse']],
                'sha256':{k:digest(m['artifacts'][k]) for k in ['product_json','source_hero','facebook_copy','linkedin_copy','social_image','social_upload']}}
        write_manifest(Path(m['artifacts']['review']),review)
        return path,m
    def publish_fixture(self,path):
        # Synthetic local evidence only; fake links are never sent to a browser or service.
        for c in IDENTITIES:
            update_manifest(path,c,'pending',submission_started=True)
            ev=self.root/f'{c}.md';ev.write_text('OFFLINE TEST FIXTURE - no real publication')
            url='https://www.facebook.com/61575467138674/posts/offline-fixture' if c=='facebook' else 'https://www.linkedin.com/feed/update/urn:li:activity:123456/'
            update_manifest(path,c,'published',url=url,identity_id=IDENTITIES[c],evidence=ev)
        return load_manifest(path)
    def test_actual_template_extraction_and_source_boundaries(self):
        p=self.product()
        self.assertEqual(p['model'],'VC-21');self.assertEqual(p['facts']['declared']['battery'],'550mAh')
        self.assertNotIn('medical',p['product_detail_text']);self.assertFalse(p['facts']['conflicts'])
    def test_conflicting_units_remain_conflicts(self):
        d,c,conf=scrape.extract_facts([('Battery','550mAh')],[('Battery','1100mAh')],'')
        self.assertIn('battery',conf);self.assertNotIn('battery',d)
    def test_catalog_traverses_late_discovered_pagination_and_dedupes(self):
        def page(product,next_page):
            return parse(f'<div class="page_content_box"><div class="item_box"><a href="/{product}.html">{product}</a></div></div><a href="{next_page}">next</a><a href="/news.html">news</a>')
        pages={scrape.PRODUCTS_URL:page('one','/products/2.html'),scrape.BASE_URL+'/products/2.html':page('two','/products/3.html'),scrape.BASE_URL+'/products/3.html':page('one','/products/index.html')}
        audit={}
        with patch.object(scrape,'fetch_html',side_effect=lambda u:pages[u]): pool=scrape.discover_candidates(audit)
        self.assertEqual(audit['page_count'],3);self.assertEqual(len(pool),2)
        self.assertFalse(any('news.html' in x['url'] for x in pool))
    def test_full_social_batch_needs_no_article(self):
        path,m=self.campaign();result=validate_campaign(m)
        self.assertEqual(result['status'],'validated');self.assertEqual(set(m['channels']),{'facebook','linkedin'})
    def test_stale_copy_blocks_submission(self):
        path,m=self.campaign();Path(m['artifacts']['facebook_copy']).write_text('Changed unreviewed text')
        with self.assertRaises(ValueError): update_manifest(path,'facebook','pending',submission_started=True)
        self.assertNotIn('publishing_started_at',load_manifest(path))
    def test_dry_run_cannot_publish(self):
        path,m=self.campaign('dry-run')
        with self.assertRaises(ValueError): update_manifest(path,'facebook','pending',submission_started=True)
    def test_wrong_identity_and_dashboard_are_rejected(self):
        path,m=self.campaign();update_manifest(path,'facebook','pending',submission_started=True)
        ev=self.root/'ev';ev.write_text('fixture')
        with self.assertRaises(ValueError): update_manifest(path,'facebook','published',url='https://www.facebook.com/61575467138674/posts/x',identity_id='wrong',evidence=ev)
        with self.assertRaises(ValueError): update_manifest(path,'facebook','published',url='https://www.facebook.com/profile.php?id=61575467138674',identity_id=IDENTITIES['facebook'],evidence=ev)
    def test_uncertain_submit_permanently_prevents_reselection(self):
        path,m=self.campaign();update_manifest(path,'facebook','pending',submission_started=True)
        update_manifest(path,'facebook','blocked',error='uncertain')
        m=load_manifest(path)
        self.assertTrue(m['channels']['facebook']['submission_started_at'])
        with self.assertRaises(ValueError): scrape.ensure_unsubmitted(m)
    def test_published_channel_cannot_be_reset(self):
        path,m=self.campaign();self.publish_fixture(path)
        with self.assertRaises(ValueError): update_manifest(path,'facebook','pending')
    def test_sheet_is_required_and_must_match_readback(self):
        path,m=self.campaign();m=self.publish_fixture(path)
        with self.assertRaises(ValueError): validate_completion(m)
        values=expected_row(m);vf=self.root/'values.json';write_manifest(vf,values)
        ev=self.root/'readback.json';write_manifest(ev,{'spreadsheet_id':SHEET_ID,'row':7,'values':values,'matching_rows':2})
        with self.assertRaises(ValueError): update_manifest(path,'google_sheet','reported',url=SHEET_URL,external_id=7,evidence=ev,values_file=vf)
        write_manifest(ev,{'spreadsheet_id':SHEET_ID,'row':7,'values':values,'matching_rows':1})
        update_manifest(path,'google_sheet','reported',url=SHEET_URL,external_id=7,evidence=ev,values_file=vf)
        Path(m['artifacts']['social_upload']).unlink()
        self.assertEqual(validate_completion(load_manifest(path))['status'],'complete')
        self.assertEqual(expected_row(load_manifest(path)),values)
    def test_candidate_budget_and_no_reuse(self):
        log_path,log=scrape.new_selection(self.root,targeted=False);log['mode']='dry-run'
        candidates=[{'url':f'https://www.vantrendtools.com/p{i}.html'} for i in range(20)]
        with patch.object(scrape,'extract_product',side_effect=ValueError('bad source')) as extract:
            with self.assertRaises(RuntimeError): scrape.select_candidate(candidates,self.root,log_path,log)
            self.assertEqual(extract.call_count,10)
        self.assertEqual(len(log['attempts']),10)
    def test_network_failure_stops_after_one_candidate(self):
        log_path,log=scrape.new_selection(self.root,targeted=False);log['mode']='dry-run'
        with patch.object(scrape,'extract_product',side_effect=RuntimeError('network unavailable')) as extract:
            with self.assertRaises(RuntimeError): scrape.select_candidate([{'url':URL},{'url':URL+'x'}],self.root,log_path,log)
            self.assertEqual(extract.call_count,1)
        self.assertEqual(log['status'],'blocked')
    def test_small_image_fails_and_metadata_is_removed(self):
        with self.assertRaises(ValueError): compress(Image.new('RGB',(100,100)),750*1024,(960,960))
        image=Image.new('RGB',(1000,1000));image.info.update(exif=b'fixture',icc_profile=b'fixture',xmp=b'fixture')
        clean=strip_metadata(image);self.assertFalse(clean.info)
        enc,_,_=compress(clean,750*1024,(960,960));p=self.root/'image.webp';p.write_bytes(enc)
        self.assertTrue(validate(p,'social',750*1024)['metadata_removed'])

if __name__=='__main__': unittest.main(verbosity=2)
