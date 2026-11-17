// Data, not interface text: the Chinese words the English-name suggestion knows (see typeModel.suggestEnglish).
export const WORDS = {
  售后: "after_sales", 工单: "ticket", 订单: "order", 客户: "customer", 产品: "product", 商品: "product", 员工: "employee", 工程师: "engineer", 供应商: "supplier",
  发票: "invoice", 付款: "payment", 支付: "payment", 退款: "refund", 库存: "inventory", 门店: "store", 用户: "user", 部门: "department", 合同: "contract",
  项目: "project", 地区: "region", 物流: "shipment", 采购: "purchase", 销售: "sales", 明细: "item", 订阅: "subscription", 设备: "device", 任务: "task", 事件: "event",
};
export const WORD_LIST = Object.keys(WORDS).sort((a, b) => b.length - a.length);

