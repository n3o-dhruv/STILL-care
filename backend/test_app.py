import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from fastapi import HTTPException
from backend import app as module

class AuthorizationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.previous=module.STORE;module.STORE=Path(self.temp.name);self.client=TestClient(module.app)
 def tearDown(self):
  module.app.dependency_overrides.clear();module.STORE=self.previous;self.temp.cleanup()
 def authenticated(self):module.app.dependency_overrides[module.identity]=lambda:{'id':'patient-a','token':'test'}
 def test_health_and_missing_token(self):
  self.assertEqual(self.client.get('/health').status_code,200)
  self.assertEqual(self.client.get('/sessions').status_code,401)
 def test_empty_history(self):
  self.authenticated();self.assertEqual(self.client.get('/sessions').json(),[])
 def test_unassigned_patient_denied(self):
  self.authenticated()
  with patch.object(module,'remote',return_value=False):self.assertEqual(self.client.get('/sessions?patient_id=patient-b').status_code,403)
 def test_assigned_patient_access(self):
  self.authenticated()
  with patch.object(module,'remote',return_value=True):self.assertEqual(self.client.get('/sessions?patient_id=patient-b').json(),[])
 def test_narrative_isolated(self):
  self.authenticated();self.assertEqual(self.client.put('/personalization',json={'narrative':'Original account'}).status_code,200)
  self.assertEqual(self.client.get('/personalization').json()['narrative'],'Original account')
  module.app.dependency_overrides[module.identity]=lambda:{'id':'patient-b','token':'test'}
  self.assertEqual(self.client.get('/personalization').json()['narrative'],'')
 def test_missing_and_invalid_artifact(self):
  self.authenticated();self.assertEqual(self.client.get('/sessions/not-a-uuid/graph').status_code,422)
  self.assertEqual(self.client.get('/sessions/00000000-0000-0000-0000-000000000000/graph').status_code,404)
 def test_model_failure_does_not_save_session(self):
  self.authenticated()
  with patch.object(module,'remote',return_value=[{'role':'patient'}]),patch.object(module,'report_module') as m:
   m.return_value.call_ollama.side_effect=RuntimeError('offline')
   self.assertEqual(self.client.post('/sessions',json={'content':'My reflection'}).status_code,503)
  self.assertEqual(self.client.get('/sessions').json(),[])
 def test_empty_reflection_rejected(self):
  self.authenticated();self.assertEqual(self.client.post('/sessions',json={'content':''}).status_code,422)
if __name__=='__main__':unittest.main()
