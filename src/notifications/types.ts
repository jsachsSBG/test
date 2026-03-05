export interface VisitorAlert {
  visitorId: string;
  intentScore: number;
  visitCount: number;
  email?: string;
  name?: string;
  company?: string;
  phone?: string;
  keyBehaviors: string[];
}
