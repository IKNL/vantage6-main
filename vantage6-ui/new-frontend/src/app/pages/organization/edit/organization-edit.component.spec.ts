import { ComponentFixture, TestBed } from '@angular/core/testing';

import { OrganizationEditComponent } from './organization-edit.component';

describe('OrganizationEditComponent', () => {
  let component: OrganizationEditComponent;
  let fixture: ComponentFixture<OrganizationEditComponent>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      declarations: [OrganizationEditComponent]
    });
    fixture = TestBed.createComponent(OrganizationEditComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
