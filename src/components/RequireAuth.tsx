import type {ReactNode} from 'react';
import { useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { profile, supabase } from '../lib/supabase';
export default function RequireAuth({role,children}:{role:string;children:ReactNode}) {
 const [state,setState]=useState('loading');
 useEffect(()=>{let active=true; const check=async()=>{try {const p=await profile(); let valid=p.role===role; if(role==='consultant'){const {data,error}=await supabase.from('consultants').select('verification_status').eq('user_id',p.user_id).single(); valid=valid&&!error&&data?.verification_status==='approved';} if(active)setState(valid?'ok':'denied');} catch {if(active)setState('denied');}};check();const {data}=supabase.auth.onAuthStateChange(()=>{setTimeout(check,0)});return()=>{active=false;data.subscription.unsubscribe()};},[role]);
 if(state==='loading')return <p role="status">Loading account?</p>;
 return state==='ok'?children:<Navigate to="/login" replace/>;
}
