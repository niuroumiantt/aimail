import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { ContactRegistrationState } from "@/data/types";
import { ContactRegistration } from "./contact-registration";
const data = vi.hoisted(() => ({contactRegistration:vi.fn(),extractContact:vi.fn(),saveContact:vi.fn()}));
vi.mock("@/data/provider", () => ({useData:()=>data}));
const defaults = {company:"",contact:"Alex",email:"alex@gmail.com",website:"",region:"",phone:"",title:"",products:"",wants:"",quantity:"",terms:"",business_role:"unknown" as const,source_type:"manual" as const,intent:"contact" as const,next_step:"",due_at:"",link_registration_id:null};
const state:ContactRegistrationState = {defaults,candidates:[],registration:null,suggestion:null,identity:{current:true,conflict:false,received_at:null,matches:[]}};
it("saves only after human confirmation and waits for a real downstream receipt", async()=>{
  data.contactRegistration.mockResolvedValue(state);
  const saved = {...state,registration:{id:1,fields:{...defaults,company:"Aurora"},receipt:{},confirmed_at:"2026-10-09"}};
  data.saveContact.mockImplementation(async()=>{data.contactRegistration.mockResolvedValue(saved);return saved;});
  render(<ContactRegistration threadId="12"/>);
  fireEvent.click(await screen.findByRole("button",{name:"建立档案"}));
  expect(data.extractContact).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("公司／项目"),{target:{value:"Aurora"}});
  await waitFor(()=>expect(screen.getByRole("button",{name:"确认建档并同步"})).toBeEnabled());
  fireEvent.click(screen.getByRole("button",{name:"确认建档并同步"}));
  await waitFor(()=>expect(data.saveContact).toHaveBeenCalledWith("12",expect.objectContaining({company:"Aurora",email:"alex@gmail.com"})));
  expect(await screen.findByRole("button",{name:"已保存 · 等待同步"})).toBeInTheDocument();
  expect(screen.queryByRole("link",{name:/查看档案与跟进/})).not.toBeInTheDocument();
});
it("shows the confirmed archive link only with a receipt",async()=>{
  data.contactRegistration.mockResolvedValue({...state,registration:{id:1,fields:defaults,receipt:{account_id:"registration_1",company_id:"company_1"},confirmed_at:"2026-10-09"}});
  render(<ContactRegistration threadId="13"/>);
  fireEvent.click(await screen.findByRole("button",{name:"已建档"}));
  const link=await screen.findByRole("link",{name:/查看档案与跟进/});
  expect(link).toHaveAttribute("href","https://leads.glocalstorage.cn/?lead=registration_1");
});
