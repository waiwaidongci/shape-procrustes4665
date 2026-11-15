export type Point=[number,number];export type Outline=Point[];
export interface User{id:number;email:string;name:string;role:'admin'|'analyst'|'viewer'}
export interface Template{id:number;code:string;name:string;labels:string[];points:Outline;convention:string;current_version?:number}
export interface TemplateVersion{id:number;template_id:number;version:number;labels:string[];points:Outline;convention:string;is_active:boolean;created_by:string;created_at:string|null}
export interface Collection{id:number;code:string;name:string;template_id:number;protocol:string;source_file:string}
export interface Specimen{id:number;collection_id?:number;code:string;name:string;points:Outline;source_note:string;template_version:number;revision?:number}
export type MigrationStatus='draft'|'in_progress'|'conflict'|'completed'|'cancelled';
export type MigrationItemStatus='pending'|'applied'|'failed'|'stale';
export interface MigrationConflict{item_id:number;specimen_id:number;code:string;status:MigrationItemStatus;message:string;recorded_version:number;recorded_revision:number;current_version:number;current_revision:number}
export interface MigrationCollectionStat{collection_id:number;total:number;applied:number;pending:number;failed:number;stale:number}
export interface MigrationSummary{total:number;applied:number;pending:number;failed:number;stale:number;collections:MigrationCollectionStat[];conflicts:MigrationConflict[]}
export interface MigrationItem{id:number;migration_id:number;specimen_id:number;collection_id:number;status:MigrationItemStatus;before_points:Outline;after_points:Outline;source_specimen_version:number;source_specimen_revision:number;message:string;specimen_code:string;specimen_name:string;collection_code:string}
export interface Migration{id:number;name:string;template_id:number;from_version_id:number;to_version_id:number;from_version:number;to_version:number;status:MigrationStatus;label_mapping:Record<string,string>;point_mapping:number[];summary:MigrationSummary;created_by:string;created_at:string|null;updated_at:string|null;finished_at:string|null;items?:MigrationItem[]}
export interface ShapeRow extends Specimen{centroid:Point;centroid_size:number;preshape:Outline;rotation:number[][];rotation_determinant:number;aligned:Outline;gpa_distance:number;scores:number[];reconstruction:Outline;residual:number}
export interface Mode{index:number;singular_value:number;eigenvalue:number;explained_ratio:number;sd:number;loading:Outline;minus_2sd:Outline;plus_2sd:Outline}
export interface PCA{arithmetic_mean:Outline;mean_norm:number;singular_values:number[];eigenvalues:number[];explained_ratio:number[];active_rank:number;retained_explained_ratio:number|null;retained:number;requested:number;noise_floor:number;has_variation:boolean;all_scores:number[][];scores:number[][];modes:Mode[];total_centered_ss:number}
export interface Snapshot{collection:Collection;template:Template;specimens:Specimen[]}
export interface Result{specimens:ShapeRow[];labels:string[];gpa_mean:Outline;gpa_mean_norm:number;reference_normalized:Outline;history:{iteration:number;objective:number;mean_delta:number|null;roundoff_increase?:boolean;roundoff_bound?:number}[];iterations:number;converged:boolean;effective_tolerance:number;termination:{reason:string;checked_iteration:number};determinant_min:number;pca:PCA;mean_difference:number;fingerprint:string;snapshot:Snapshot;scope:string}
export interface Run{id:number;name:string;collection_id:number;retained:number;tolerance:number;status:'queued'|'running'|'completed'|'failed';snapshot:Snapshot;result:Result;error:string;created_at:string}
export interface Note{id:number;name:string;run_id:number;specimen_id:number;protocol:string;status:'draft'|'approved'|'rejected';reviewer_note:string;reviewed_by:string;created_at:string}
