import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';

import { Rule } from 'src/app/interfaces/rule';
import { Role } from 'src/app/interfaces/role';
import { User } from 'src/app/interfaces/user';

import { environment } from 'src/environments/environment';
import { getIdsFromArray } from 'src/app/utils';
import { RoleService } from './role.service';
import { RuleService } from './rule.service';
import { ConvertJsonService } from '../convert-json.service';

@Injectable({
  providedIn: 'root',
})
export class UserService {
  all_rules: Rule[] = [];

  constructor(
    private http: HttpClient,
    private roleService: RoleService,
    private ruleService: RuleService,
    private convertJsonService: ConvertJsonService
  ) {
    this.setup();
  }

  async setup(): Promise<void> {
    this.all_rules = await this.ruleService.getAllRules();
  }

  list(organization_id: number | null = null) {
    let params: any = {};
    if (organization_id !== null) {
      params['organization_id'] = organization_id;
    }
    return this.http.get(environment.api_url + '/user', { params: params });
  }

  get(id: number) {
    return this.http.get<any>(environment.api_url + '/user/' + id);
  }

  update(user: User) {
    let data = this._get_data(user);
    return this.http.patch<any>(environment.api_url + '/user/' + user.id, data);
  }

  create(user: User) {
    const data = this._get_data(user);
    return this.http.post<any>(environment.api_url + '/user', data);
  }

  delete(user: User) {
    return this.http.delete<any>(environment.api_url + '/user/' + user.id);
  }

  private _get_data(user: User): any {
    let data: any = {
      username: user.username,
      email: user.email,
      firstname: user.first_name,
      lastname: user.last_name,
      organization_id: user.organization_id,
      roles: getIdsFromArray(user.roles),
      rules: getIdsFromArray(user.rules),
    };
    if (user.password) {
      data.password = user.password;
    }
    return data;
  }

  async getUserJson(id: number): Promise<any> {
    // TODO remove this func
    return await this.get(id).toPromise();
  }

  async getUser(id: number): Promise<User> {
    let user_json = await this.get(id).toPromise();

    console.log(user_json);
    let role_ids: number[] = [];
    if (user_json.roles) {
      role_ids = getIdsFromArray(user_json.roles);
    }
    let roles = await this.roleService.getRoles(role_ids);

    return this.convertJsonService.getUser(user_json, roles, this.all_rules);
  }
}
