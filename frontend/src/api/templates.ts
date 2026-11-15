import {request,post} from './client';import type {Template,TemplateVersion} from '../types/domain';export const list=()=>request<Template[]>('/templates'+'');export const create=(data:unknown)=>post<Template>('/templates',data);
export const update=(id:number,data:unknown)=>request<Template>('/templates/'+id,{method:'PUT',body:JSON.stringify(data)});
export const versions=(id:number)=>request<TemplateVersion[]>('/templates/'+id+'/versions');
