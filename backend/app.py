"""Authenticated local-first API. Never mount the unauthenticated intelligence API publicly."""
import importlib.util
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from functools import lru_cache
from contextlib import contextmanager
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env.local')
load_dotenv(ROOT/'.env')
URL=os.getenv('SUPABASE_URL',os.getenv('VITE_SUPABASE_URL','')).rstrip('/')
KEY=os.getenv('SUPABASE_PUBLISHABLE_KEY',os.getenv('VITE_SUPABASE_PUBLISHABLE_KEY',''))
STORE=Path(os.getenv('STILL_PRIVATE_DIR',str(ROOT/'data'/'private'))).resolve()
STORE.mkdir(parents=True,exist_ok=True)
app=FastAPI(title='STILL-care authenticated local API')
app.add_middleware(CORSMiddleware,allow_origins=os.getenv('FRONTEND_ORIGINS','http://localhost:3000,http://127.0.0.1:3000').split(','),allow_methods=['GET','POST','PUT','PATCH'],allow_headers=['Authorization','Content-Type'])
@contextmanager
def db():
 c=sqlite3.connect(STORE/'sessions.sqlite');c.row_factory=sqlite3.Row
 c.execute('create table if not exists sessions(id text primary key,patient text not null,date text not null,summary text not null,report text not null)')
 c.execute('create table if not exists personalization(patient text primary key,narrative text not null)')
 c.execute('create table if not exists records(id text primary key,patient text not null,kind text not null,payload text not null)')
 try:
  with c:yield c
 finally:c.close()

def remote(path,token,method='GET',body=None):
 try:
  r=httpx.request(method,URL+path,headers={'apikey':KEY,'Authorization':'Bearer '+token},json=body,timeout=15)
 except httpx.RequestError:raise HTTPException(503,'Identity service unavailable')
 if r.status_code>=400:raise HTTPException(401 if r.status_code==401 else 403,'Identity or authorization request failed')
 return r.json() if r.content else None

def identity(authorization:str=Header(default='')):
 if not URL or not KEY:raise HTTPException(503,'Supabase environment is missing')
 if not authorization.startswith('Bearer ') or not authorization[7:]:raise HTTPException(401,'Bearer token required')
 token=authorization[7:];u=remote('/auth/v1/user',token)
 if not u.get('email_confirmed_at'):raise HTTPException(403,'Verified email required')
 return {'id':u['id'],'token':token}

def access(user,patient=None):
 patient=patient or user['id']
 if patient!=user['id']:
  ok=remote('/rest/v1/rpc/can_access_patient',user['token'],'POST',{'patient':patient})
  if ok is not True:raise HTTPException(403,'Patient is not assigned to you')
 return patient

def session_view(row):
 report=json.loads(row['report']);scores=[s['distress_score'] for s in report.get('segments',[])]
 return {'id':row['id'],'patientId':row['patient'],'date':row['date'][:10],'mode':'text','summary':row['summary'],'plainLanguageReason':report.get('patient_message',''),'riskLevel':'neutral','distressTrend':'unknown','distressScore':scores[-1] if scores else None}

@app.get('/health')
def health():return {'status':'ok','inference':'not checked'}
@app.get('/sessions')
def sessions(patient_id:str|None=None,user=Depends(identity)):
 patient=access(user,patient_id)
 with db() as c:return [session_view(r) for r in c.execute('select * from sessions where patient=? order by date desc',(patient,))]
class Reflection(BaseModel):
 content:str=Field(min_length=1,max_length=20000)
@lru_cache
def report_module():
 spec=importlib.util.spec_from_file_location('still_report',ROOT/'chatbot/04_chat_llm/chat_llm.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
@app.post('/sessions',status_code=201)
def complete_session(body:Reflection,user=Depends(identity)):
 profiles=remote('/rest/v1/profiles?select=role&user_id=eq.'+user['id'],user['token'])
 if not profiles or profiles[0]['role']!='patient':raise HTTPException(403,'Patient account required')
 if not body.content.strip():raise HTTPException(422,'Reflection is empty')
 m=report_module()
 # Text input has no acoustic evidence. No fabricated voice measurements.
 segments=[{'start':0,'end':0,'text':body.content,'acoustic_features':{'pitch_available':False,'audio_status':'unavailable'},'speech_emotion_status':'unverified'}]
 with db() as c:background=c.execute('select narrative from personalization where patient=?',(user['id'],)).fetchone()
 facts_path=STORE/'profiles'/user['id']/'case_facts.json'
 context={'original_narrative':background['narrative'] if background else '', 'extracted_facts':json.loads(facts_path.read_text()) if facts_path.exists() else {}}
 try:result=m.call_ollama(segments,contextual_data=context)
 except Exception:raise HTTPException(503,'Local report model unavailable or returned invalid data; session was not saved')
 if not isinstance(result.get('segments'),list) or not result['segments'] or not isinstance(result.get('clinician_summary'),str):raise HTTPException(502,'Invalid model report')
 for s in result['segments']:
  if not isinstance(s,dict) or type(s.get('distress_score')) not in (float,int) or not 0<=s['distress_score']<=10 or not isinstance(s.get('start'),(int,float)):raise HTTPException(502,'Invalid assessment')
 sid=str(uuid.uuid4());folder=STORE/sid;folder.mkdir()
 try:m.save_report_and_graph(result,str(folder))
 except Exception:raise HTTPException(503,'Unable to save report artifacts')
 now=datetime.now(timezone.utc).isoformat()
 with db() as c:
  c.execute('insert into sessions values(?,?,?,?,?)',(sid,user['id'],now,result['clinician_summary'],json.dumps(result)))
  row=c.execute('select * from sessions where id=?',(sid,)).fetchone()
 return session_view(row)

@app.get('/sessions/{sid}/{artifact}')
def artifact(sid:uuid.UUID,artifact:str,user=Depends(identity)):
 if artifact not in ('report','graph'):raise HTTPException(404)
 with db() as c:row=c.execute('select * from sessions where id=?',(str(sid),)).fetchone()
 if not row:raise HTTPException(404)
 access(user,row['patient'])
 if artifact=='report':return json.loads(row['report'])
 return FileResponse(STORE/str(sid)/'mental_state.png',media_type='image/png')
class Personalization(BaseModel):
 narrative:str=Field(max_length=20000)
@app.get('/personalization')
def personalization(user=Depends(identity)):
 with db() as c:r=c.execute('select narrative from personalization where patient=?',(user['id'],)).fetchone()
 return {'narrative':r['narrative'] if r else ''}
@app.put('/personalization')
def save_personalization(body:Personalization,user=Depends(identity)):
 with db() as c:c.execute('insert into personalization values(?,?) on conflict(patient) do update set narrative=excluded.narrative',(user['id'],body.narrative))
 return {'saved':True}

@app.get('/messages')
@app.get('/actions')
def records(patient_id:str|None=None,user=Depends(identity)):
 # These workflows have not been implemented; never fabricate successful responses.
 raise HTTPException(501,'Messaging and appointment workflows are not yet configured')
@app.get('/alerts')
def alerts(user=Depends(identity)):
 # No automatic clinical threshold has been approved; no distress alerts are generated.
 return []
@app.get('/recommendations')
def recommendations(user=Depends(identity)):return []

@app.post('/personalization/extract')
def extract_profile(user=Depends(identity)):
 with db() as c:r=c.execute('select narrative from personalization where patient=?',(user['id'],)).fetchone()
 if not r or not r['narrative'].strip():raise HTTPException(422,'Save a narrative first')
 spec=importlib.util.spec_from_file_location('still_case',ROOT/'chatbot/06_case_profile/case_profile.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 folder=STORE/'profiles'/user['id'];folder.mkdir(parents=True,exist_ok=True)
 facts_path=folder/'case_facts.json'
 existing=json.loads(facts_path.read_text()) if facts_path.exists() else None
 try:facts=m.extract_and_merge_case_facts(r['narrative'],existing_facts=existing)
 except Exception:raise HTTPException(503,'Local case profile extraction unavailable')
 temporary=folder/(str(uuid.uuid4())+'.tmp');temporary.write_text(json.dumps(facts),encoding='utf-8');temporary.replace(facts_path)
 return {'extracted':True}
