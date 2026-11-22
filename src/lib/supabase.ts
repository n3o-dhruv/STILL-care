import { createClient } from '@supabase/supabase-js';
const url = import.meta.env.VITE_SUPABASE_URL;
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;
export const configurationError = !url || !key ? 'Configure VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY in .env.local.' : null;
export const supabase = createClient(url || 'https://unconfigured.supabase.co', key || 'unconfigured', { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } });
export async function identity() {
 if(configurationError) throw new Error(configurationError);
 const {data,error}=await supabase.auth.getUser(); if(error || !data.user) throw error || new Error('Sign in required'); return data.user;
}
export async function profile() { const u=await identity(); const {data,error}=await supabase.from('profiles').select('*').eq('user_id',u.id).single(); if(error) throw error; return {...data,email:u.email}; }
export async function logout() { const {error}=await supabase.auth.signOut(); if(error) throw error; window.location.assign('/login'); }
export async function localApi(path:string, options:RequestInit={}) { const {data}=await supabase.auth.getSession(); const r=await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}${path}`,{...options,headers:{'Content-Type':'application/json',Authorization:`Bearer ${data.session?.access_token || ''}`,...options.headers}}); if(!r.ok) throw new Error((await r.json()).detail || 'Backend request failed'); return r.json(); }
