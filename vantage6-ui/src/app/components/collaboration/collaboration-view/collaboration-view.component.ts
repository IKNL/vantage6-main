import { Component, EventEmitter, Input, OnInit, Output } from '@angular/core';

import {
  Collaboration,
  EMPTY_COLLABORATION,
} from 'src/app/interfaces/collaboration';
import { getEmptyNode } from 'src/app/interfaces/node';

import { UserPermissionService } from 'src/app/auth/services/user-permission.service';
import { OrganizationInCollaboration } from 'src/app/interfaces/organization';
import { Router } from '@angular/router';
import { NodeStoreService } from 'src/app/services/store/node-store.service';
import { OpsType, ResType } from 'src/app/shared/enum';
import { ApiNodeService } from 'src/app/services/api/api-node.service';
import { ModalService } from 'src/app/services/common/modal.service';
import { ModalMessageComponent } from '../../modal/modal-message/modal-message.component';
import {
  removeMatchedIdFromArray,
  removeMatchedIdsFromArray,
} from 'src/app/shared/utils';
import { ConvertJsonService } from 'src/app/services/common/convert-json.service';

@Component({
  selector: 'app-collaboration-view',
  templateUrl: './collaboration-view.component.html',
  styleUrls: [
    '../../../shared/scss/buttons.scss',
    './collaboration-view.component.scss',
  ],
})
export class CollaborationViewComponent implements OnInit {
  // TODO update the collaboration if e.g. a node is deleted, now the view is
  // not  updated then
  @Input() collaboration: Collaboration = EMPTY_COLLABORATION;
  @Output() deletingCollab = new EventEmitter<Collaboration>();
  @Output() editingCollab = new EventEmitter<Collaboration>();
  orgs_without_nodes: OrganizationInCollaboration[] = [];

  constructor(
    private router: Router,
    public userPermission: UserPermissionService,
    private nodeStoreService: NodeStoreService,
    private apiNodeService: ApiNodeService,
    private modalService: ModalService,
    private convertJsonService: ConvertJsonService
  ) {}

  ngOnInit(): void {
    this.setMissingNodes();
  }

  encrypted(): string {
    return this.collaboration.encrypted ? 'Yes' : 'No';
  }

  getButtonClasses(org: OrganizationInCollaboration): string {
    let default_classes = 'mat-button btn-detail inline ';
    if (!org.node) return default_classes;
    else if (org.node.is_online) return default_classes + 'btn-online';
    else return default_classes + 'btn-offline';
  }

  setMissingNodes(): void {
    this.orgs_without_nodes = [];
    for (let org of this.collaboration.organizations) {
      if (!org.node) {
        this.orgs_without_nodes.push(org);
      }
    }
  }

  isDisabled(org: OrganizationInCollaboration): boolean {
    return (
      org.node === undefined ||
      !this.userPermission.can(OpsType.VIEW, ResType.NODE, org.id)
    );
  }

  goToNode(org: OrganizationInCollaboration): void {
    if (org.node) {
      this.nodeStoreService.setNode(org.node);
      this.router.navigate([`/node/${org.node.id}/view/${org.id}`]);
    }
  }

  createNode(org: OrganizationInCollaboration): void {
    let new_node = getEmptyNode();
    new_node.name = `${this.collaboration.name} - ${org.name}`;
    new_node.organization_id = org.id;
    new_node.collaboration_id = this.collaboration.id;
    this.apiNodeService.create(new_node).subscribe(
      (node_json) => {
        this.modalService.openMessageModal(ModalMessageComponent, [
          `The node '${node_json.name}' has been created! You can now generate a
configuration file for the node using 'vnode new'.`,
          'Please insert the following API key into your configuration file:',
          node_json.api_key,
        ]);
        // Remove the organization from organizations for which no node is
        // present
        this.orgs_without_nodes = removeMatchedIdFromArray(
          this.orgs_without_nodes,
          org.id
        );
        // set the new node as part of the organization
        org.node = this.convertJsonService.getNode(node_json);
      },
      (error) => {
        this.modalService.openMessageModal(ModalMessageComponent, [
          'Error:',
          error.error.msg,
        ]);
      }
    );
  }
}
