import { Injectable } from '@angular/core';
import { Result } from 'src/app/interfaces/result';
import { ResultApiService } from '../api/result-api.service';
import { ConvertJsonService } from '../common/convert-json.service';
import { BaseDataService } from './base-data.service';

@Injectable({
  providedIn: 'root',
})
export class ResultDataService extends BaseDataService {
  queried_task_ids: number[] = [];

  constructor(
    protected apiService: ResultApiService,
    protected convertJsonService: ConvertJsonService
  ) {
    super(apiService, convertJsonService);
  }

  async get_by_task_id(
    task_id: number,
    force_refresh: boolean = false
  ): Promise<Result[]> {
    let results: Result[] = [];
    if (force_refresh) {
      // TODO add function to API service to get resources by task ID
      results = await this.apiService.getResourcesByTaskId(task_id);
      this.queried_task_ids.push(task_id);
      this.saveMultiple(results);
    } else {
      // this task has been queried before: get matches from the saved data
      for (let r of this.resource_list.value) {
        if ((r as Result).task_id === task_id) {
          results.push(r as Result);
        }
      }
    }
    return results;
  }

  save(result: Result) {
    // don't save organization along with result as this can lead to loop
    // of saves when then the organization is updated, then result again, etc
    if (result.organization) result.organization = undefined;
    super.save(result);
  }
}
