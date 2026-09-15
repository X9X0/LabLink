/**
 * LabLink Mobile - Navigation route types
 *
 * The screens and the parameters each one takes. Without this the navigator is
 * untyped, `navigation.navigate` accepts `never`, and callers reach for
 * `as never` to get past it -- which silences the checker rather than telling
 * it anything, and would not have caught a renamed route or a missing param.
 */

export type RootStackParamList = {
  Login: undefined;
  MainTabs: undefined;
  EquipmentDetail: { equipmentId: string };
};
