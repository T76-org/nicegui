import mermaid from "mermaid/mermaid.esm.min.mjs";
export default {
  template: `<div></div>`,
  mounted() {
    this.update(this.content);
  },
  methods: {
    async update(content) {
      this.$el.innerHTML = content;
      this.$el.removeAttribute("data-processed");
      await mermaid.run({ nodes: [this.$el] });
    },
  },
  props: {
    content: String,
  },
};
