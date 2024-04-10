import { HttpErrorResponse } from '@angular/common/http';
import { Component, HostBinding, Input, OnDestroy, OnInit } from '@angular/core';
import { MatDialog } from '@angular/material/dialog';
import { Router } from '@angular/router';
import { TranslateService } from '@ngx-translate/core';
import { Subject, takeUntil } from 'rxjs';
import { ConfirmDialogComponent } from 'src/app/components/dialogs/confirm/confirm-dialog.component';
import { Organization } from 'src/app/models/api/organization.model';
import { Role, RoleLazyProperties } from 'src/app/models/api/role.model';
import { OperationType, ResourceType, Rule, ScopeType } from 'src/app/models/api/rule.model';
import { TableData } from 'src/app/models/application/table.model';
import { routePaths } from 'src/app/routes';
import { OrganizationService } from 'src/app/services/organization.service';
import { PermissionService } from 'src/app/services/permission.service';
import { RoleService } from 'src/app/services/role.service';
import { RuleService } from 'src/app/services/rule.service';

@Component({
  selector: 'app-role-read',
  templateUrl: './role-read.component.html',
  styleUrls: ['./role-read.component.scss']
})
export class RoleReadComponent implements OnInit, OnDestroy {
  @HostBinding('class') class = 'card-container';
  @Input() id = '';
  destroy$ = new Subject();

  canEdit = false;
  canDelete = false;
  isLoading = true;
  isEditing: boolean = false;

  role?: Role;
  roleRules: Rule[] = [];
  roleOrganization?: Organization;
  allRules: Rule[] = [];
  userTable?: TableData;

  /* Bound variables to permission matrix. */
  preselectedRules: Rule[] = [];
  selectableRules: Rule[] = [];
  fixedSelectedRules: Rule[] = [];

  changedRules?: Rule[];
  errorMessage?: string;

  constructor(
    private dialog: MatDialog,
    private router: Router,
    private roleService: RoleService,
    private ruleService: RuleService,
    private organizationService: OrganizationService,
    private translateService: TranslateService,
    private permissionService: PermissionService
  ) {}

  async ngOnInit(): Promise<void> {
    this.allRules = await this.ruleService.getAllRules();
    try {
      await this.initData();
    } catch (error) {
      this.handleHttpError(error as HttpErrorResponse);
      this.isLoading = false;
    }
  }

  ngOnDestroy(): void {
    this.destroy$.next(true);
  }

  private handleHttpError(error: HttpErrorResponse): void {
    this.errorMessage = error.error['msg'] ?? error.message;
  }

  private async initData(): Promise<void> {
    this.role = await this.roleService.getRole(this.id, [RoleLazyProperties.Users]);
    this.setPermissions();
    const organizationId = this.role.organization?.id.toString();
    if (organizationId) {
      this.roleOrganization = await this.organizationService.getOrganization(organizationId as string);
    }
    this.userTable = {
      columns: [
        { id: 'username', label: this.translateService.instant('user.username') },
        { id: 'firstname', label: this.translateService.instant('user.first-name') },
        { id: 'lastname', label: this.translateService.instant('user.last-name') },
        { id: 'email', label: this.translateService.instant('user.email') }
      ],
      rows: this.role.users.map((user) => ({
        id: user.id.toString(),
        columnData: { ...user }
      }))
    };
    this.roleRules = await this.ruleService.getAllRules(this.id);
    this.enterEditMode(false);
    this.isLoading = false;
  }

  private enterEditMode(edit: boolean): void {
    this.isEditing = edit;
    if (edit) {
      this.preselectedRules = this.roleRules;
      this.fixedSelectedRules = [];
      this.selectableRules = this.allRules;
    } else {
      this.preselectedRules = [];
      this.fixedSelectedRules = this.roleRules;
      this.selectableRules = this.roleRules;
    }
  }

  public handleDeleteRole(): void {
    if (!this.role) return;

    const dialogRef = this.dialog.open(ConfirmDialogComponent, {
      data: {
        title: this.translateService.instant('role-read.delete-dialog.title', { name : this.role.name }),
        content: this.translateService.instant('role-read.delete-dialog.content'),
        confirmButtonText: this.translateService.instant('general.delete'),
        confirmButtonType: 'warn',
      }
    });

    dialogRef
    .afterClosed()
    .pipe(takeUntil(this.destroy$))
    .subscribe(async (result) => {
      if (result === true) {
        if (!this.role) return;
        this.isLoading = true;
        await this.roleService.deleteRole(this.role.id);
        this.router.navigate([routePaths.roles]);
      }
    });
  }

  public handleEnterEditMode(): void {
    this.enterEditMode(true);
  }

  public handleCancelEdit(): void {
    this.enterEditMode(false);
  }

  public get showData(): boolean {
    return !this.isLoading && this.role != undefined;
  }

  public get showUserTable(): boolean {
    return this.userTable != undefined && this.userTable.rows.length > 0;
  }

  public handleChangedSelection(rules: Rule[]): void {
    this.changedRules = rules;
  }

  // TODO: handle error
  public async handleSubmitEdit(): Promise<void> {
    if (!this.role || !this.changedRules) return;

    this.isLoading = true;
    const role: Role = { ...this.role, rules: this.changedRules };
    await this.roleService.patchRole(role);
    this.changedRules = [];
    this.initData();
  }

  public get editEnabled(): boolean {
    return this.canEdit && !this.role?.is_default_role;
  }

  public get deleteEnabled(): boolean {
    return this.canDelete && !this.role?.is_default_role;
  }

  public get submitDisabled(): boolean {
    return this.changedRules?.length === 0;
  }

  getDefaultRoleLabel(): string {
    if (!this.role) return '';
    return this.role.is_default_role ? this.translateService.instant('general.yes') : this.translateService.instant('general.no');
  }

  private setPermissions() {
    this.permissionService
      .isInitialized()
      .pipe(takeUntil(this.destroy$))
      .subscribe((initialized) => {
        if (initialized && this.role) {
          this.canEdit = this.permissionService.isAllowedForOrg(ResourceType.ROLE, OperationType.EDIT, this.role.organization?.id || null);
          this.canDelete = this.permissionService.isAllowedForOrg(ResourceType.ROLE, OperationType.DELETE, this.role.organization?.id || null);
        }
      });
  }
}
