import {profile,supabase,localApi} from '../lib/supabase';
import type {Supervisor,SupervisorPatient,SupervisorSessionSummary,TrendPoint,SupervisorAlert,RecommendationItem,Message,SupervisorActionRecord} from '../types';
export async function getSupervisorProfile(_id?:string):Promise<Supervisor>{const p=await profile();return {id:p.user_id,name:p.full_name,title:'Consultant',organization:'',verificationStatus:'verified'};}
export async function getSupervisorPatients():Promise<SupervisorPatient[]>{const {data,error}=await supabase.from('consultant_assignments').select('patient_id');if(error)throw error;return Promise.all((data||[]).map(async a=>{const {data:p,error}=await supabase.from('profiles').select('*').eq('user_id',a.patient_id).single();if(error)throw error;return {id:p.user_id,name:p.full_name,assignedSupervisorId:'',lastCheckInDate:'',currentRiskLevel:'neutral' as any,distressTrend:'unknown' as any};}));}
export async function getSupervisorPatient(id:string){return (await getSupervisorPatients()).find(p=>p.id===id);}
export async function getSupervisorPatientSessions(id:string):Promise<SupervisorSessionSummary[]>{return localApi('/sessions?patient_id='+encodeURIComponent(id));}
export const getPatients=getSupervisorPatients;export const getPatientById=getSupervisorPatient;export const getPatientSessionSummaries=getSupervisorPatientSessions;
export async function getPatientTrend(id:string):Promise<TrendPoint[]>{return (await getSupervisorPatientSessions(id)).map(s=>({date:s.date,checkInId:s.id,riskLevel:s.riskLevel,distressTrend:s.distressTrend}));}
export async function getSupervisorAlerts():Promise<SupervisorAlert[]>{return localApi('/alerts');}export const getAlerts=getSupervisorAlerts;
export async function markAlertReviewed(id:string){const {error}=await supabase.from('notifications').update({read_at:new Date().toISOString()}).eq('notification_id',id);if(error)throw error;}export const markAlertAsRead=markAlertReviewed;
export async function getSupervisorRecommendations():Promise<RecommendationItem[]>{return localApi('/recommendations');}export const getRecommendations=getSupervisorRecommendations;
export async function updateRecommendationStatus(id:string,status:string):Promise<void>{return localApi('/recommendations/'+id,{method:'PATCH',body:JSON.stringify({status})});}
export async function getMessages(id:string):Promise<Message[]>{return [];}
export async function sendMessage(p:any):Promise<Message>{return localApi('/messages',{method:'POST',body:JSON.stringify(p)});}
export async function logSupervisorAction(p:any):Promise<SupervisorActionRecord>{return localApi('/actions',{method:'POST',body:JSON.stringify(p)});}
export async function getSupervisorActions(id:string):Promise<SupervisorActionRecord[]>{return [];}
