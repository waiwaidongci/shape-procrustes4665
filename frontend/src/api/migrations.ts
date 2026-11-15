import {request,post} from './client';
import type {Migration,MigrationItem} from '../types/domain';
export const list=()=>request<Migration[]>('/migrations');
export const create=(data:unknown)=>post<Migration>('/migrations',data);
export const detail=(id:number)=>request<Migration>('/migrations/'+id);
export const activate=(id:number)=>post<Migration>('/migrations/'+id+'/activate',{});
export const rebase=(id:number,itemId:number)=>post<Migration>(`/migrations/${id}/items/${itemId}/rebase`,{});
export const cancel=(id:number)=>post<Migration>('/migrations/'+id+'/cancel',{});
export type {Migration,MigrationItem};
