import { Component, HostBinding, OnDestroy, OnInit } from '@angular/core';
import { BaseNode, Node, NodeEdit, NodeLazyProperties, NodeSortProperties, NodeStatus } from 'src/app/models/api/node.model';
import { NodeService } from 'src/app/services/node.service';
import { OrganizationSortProperties } from 'src/app/models/api/organization.model';
import { OrganizationService } from 'src/app/services/organization.service';
import { CollaborationService } from 'src/app/services/collaboration.service';
import { CollaborationSortProperties } from 'src/app/models/api/collaboration.model';
import { FormControl, Validators } from '@angular/forms';
import { OperationType, ResourceType } from 'src/app/models/api/rule.model';
import { Pagination, PaginationLinks } from 'src/app/models/api/pagination.model';
import { PageEvent } from '@angular/material/paginator';
import { PermissionService } from 'src/app/services/permission.service';
import { SocketioConnectService } from 'src/app/services/socketio-connect.service';
import { NodeOnlineStatusMsg } from 'src/app/models/socket-messages.model';
import { Subscription } from 'rxjs';
import { MatDialog } from '@angular/material/dialog';
import { TranslateService } from '@ngx-translate/core';
import { MessageDialogComponent } from 'src/app/components/dialogs/message-dialog/message-dialog.component';
import { FileService } from 'src/app/services/file.service';
import { printDate } from 'src/app/helpers/general.helper';
import { ITreeInputNode, ITreeSelectedValue } from 'src/app/components/helpers/tree-dropdown/tree-dropdown.component';

@Component({
  selector: 'app-node-read',
  templateUrl: './node-read.component.html',
  styleUrls: ['./node-read.component.scss']
})
export class NodeReadComponent implements OnInit, OnDestroy {
  @HostBinding('class') class = 'card-container';
  nodeStatus = NodeStatus;
  printDate = printDate;

  treeNodes: ITreeInputNode[] = [];
  selectedTreeNodes: ITreeSelectedValue[] = [];

  name = new FormControl<string>('', [Validators.required]);
  isLoading: boolean = true;
  isEdit: boolean = false;
  nodes: BaseNode[] = [];
  selectedNode?: Node;
  pagination: PaginationLinks | null = null;
  currentPage: number = 1;

  private nodeStatusUpdateSubscription?: Subscription;

  constructor(
    private dialog: MatDialog,
    private nodeService: NodeService,
    private organizationService: OrganizationService,
    private collaborationService: CollaborationService,
    private permissionService: PermissionService,
    private socketioConnectService: SocketioConnectService,
    private translateService: TranslateService,
    private fileService: FileService
  ) { }

  async ngOnInit(): Promise<void> {
    await this.initData();
    this.nodeStatusUpdateSubscription = this.socketioConnectService
      .getNodeStatusUpdates()
      .subscribe((nodeStatusUpdate: NodeOnlineStatusMsg | null) => {
        if (nodeStatusUpdate) this.onNodeStatusUpdate(nodeStatusUpdate);
      });
  }

  ngOnDestroy(): void {
    this.nodeStatusUpdateSubscription?.unsubscribe();
  }

  async handleSelectedTreeNodesChange(newSelected: ITreeSelectedValue[]): Promise<void> {
    this.selectedTreeNodes = newSelected.length ? [newSelected[0]] : [];
    await this.getNodes(newSelected[0]);
  }

  async handlePageEvent(e: PageEvent) {
    this.currentPage = e.pageIndex + 1;
    await this.getNodes();
  }

  async handleNodeChange(nodeID: number): Promise<void> {
    this.isEdit = false;
    await this.getNode(nodeID);
  }

  handleEditStart(): void {
    this.isEdit = true;
  }

  async handleEditSubmit(): Promise<void> {
    if (!this.selectedNode || !this.name.value) return;

    this.isEdit = false;
    const nodeEdit: NodeEdit = {
      name: this.name.value
    };
    const result = await this.nodeService.editNode(this.selectedNode.id.toString(), nodeEdit);
    if (result.id) {
      this.selectedNode.name = result.name;
      const nodeToUpdate = this.nodes.find((node) => node.id === result.id);
      if (nodeToUpdate) {
        nodeToUpdate.name = result.name;
      }
    }
  }

  handleEditCancel(): void {
    this.isEdit = false;
  }

  canEdit(orgId: number): boolean {
    return this.permissionService.isAllowedForOrg(ResourceType.NODE, OperationType.EDIT, orgId);
  }

  onNodeStatusUpdate(nodeStatusUpdate: NodeOnlineStatusMsg): void {
    for (const node of this.nodes) {
      if (node.id === nodeStatusUpdate.id) {
        node.status = nodeStatusUpdate.online ? NodeStatus.Online : NodeStatus.Offline;
        if (this.selectedNode && this.selectedNode.id === node.id) {
          this.selectedNode.status = node.status;
        }
        break;
      }
    }
  }

  async generateNewAPIKey(): Promise<void> {
    if (!this.selectedNode) return;
    const new_api_key = await this.nodeService.resetApiKey(this.selectedNode?.id.toString());
    this.downloadResettedApiKey(new_api_key.api_key, this.selectedNode.name);

    this.dialog.open(MessageDialogComponent, {
      data: {
        title: this.translateService.instant('api-key-download-dialog.title'),
        content: [this.translateService.instant('api-key-download-dialog.reset-message')],
        confirmButtonText: this.translateService.instant('general.close'),
        confirmButtonType: 'default'
      }
    });
  }

  private downloadResettedApiKey(api_key: string, node_name: string): void {
    const filename = `API_key_${node_name}.txt`;
    this.fileService.downloadTxtFile(api_key, filename);
  }

  private async initData(): Promise<void> {
    this.isLoading = true;

    const loadOrganizations = this.organizationService.getOrganizations({ sort: OrganizationSortProperties.Name });
    const loadCollaborations = await this.collaborationService.getCollaborations({ sort: CollaborationSortProperties.Name });
    await Promise.all([loadOrganizations, loadCollaborations, this.getNodes()]).then((values) => {
      this.treeNodes = [
        {
          isFolder: true,
          children: values[0].map((organization) => {
            return {
              isFolder: false,
              children: [],
              label: organization.name,
              code: organization.id,
              parentCode: 'organization'
            };
          }),
          label: this.translateService.instant('node.organization'),
          code: 'organization'
        },
        {
          isFolder: true,
          children: values[1].map((collaboration) => {
            return {
              isFolder: false,
              children: [],
              label: collaboration.name,
              code: collaboration.id,
              parentCode: 'collaboration'
            };
          }),
          label: this.translateService.instant('node.collaboration'),
          code: 'collaboration'
        }
      ];
    });
    this.isLoading = false;
  }

  private async getNode(nodeID: number): Promise<void> {
    this.selectedNode = undefined;
    this.selectedNode = await this.nodeService.getNode(nodeID.toString(), [
      NodeLazyProperties.Organization,
      NodeLazyProperties.Collaboration
    ]);
    this.name.setValue(this.selectedNode.name);
  }

  private async getNodes(selectedValue?: ITreeSelectedValue): Promise<void> {
    let result: Pagination<BaseNode> | null = null;
    if (selectedValue && selectedValue.parentCode === 'organization') {
      result = await this.nodeService.getPaginatedNodes(this.currentPage, {
        organization_id: selectedValue.code.toString(),
        sort: NodeSortProperties.Name
      });
    } else if (selectedValue && selectedValue.parentCode === 'collaboration') {
      result = await this.nodeService.getPaginatedNodes(this.currentPage, {
        collaboration_id: selectedValue.code.toString(),
        sort: NodeSortProperties.Name
      });
    } else {
      result = await this.nodeService.getPaginatedNodes(this.currentPage, { sort: NodeSortProperties.Name });
    }
    this.nodes = result.data;
    this.pagination = result.links;
  }
}
