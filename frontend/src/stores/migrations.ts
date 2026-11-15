import {createStore} from '../utils/store';
import * as api from '../api/migrations';
import type {Migration} from '../types/domain';

export const migrationStore=createStore<{items:Migration[];selected:number;detail:Migration|null}>({items:[],selected:Number(localStorage.getItem('shapes-migration')||0),detail:null});

export async function loadMigrations(){
  const items=await api.list();
  let selected=migrationStore.get().selected;
  if(!items.some(m=>m.id===selected))selected=items[0]?.id||0;
  migrationStore.set({items,selected});
  if(selected)await loadDetail(selected);
}
export async function loadDetail(id:number){
  localStorage.setItem('shapes-migration',String(id));
  const detail=await api.detail(id);
  migrationStore.set({selected:id,detail});
}
export function selectMigration(id:number){loadDetail(id).catch(()=>{});}
export async function createMigration(data:unknown){
  const m=await api.create(data);await loadMigrations();await loadDetail(m.id);return m;
}
export async function activateMigration(id:number){const m=await api.activate(id);await loadDetail(id);await loadMigrations();return m;}
export async function rebaseItem(id:number,itemId:number){const m=await api.rebase(id,itemId);await loadDetail(id);await loadMigrations();return m;}
export async function cancelMigration(id:number){const m=await api.cancel(id);await loadDetail(id);await loadMigrations();return m;}
