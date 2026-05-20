const posts = [
  {
    title: "把最近的日子整理成一页纸",
    date: "2026-05-20",
    excerpt:
      "写博客的第一步，也许不是写一篇很完整的文章，而是给自己留一个可以慢慢返回的地方。",
    tag: "生活",
    url: "#",
  },
  {
    title: "一个安静周末里的小项目",
    date: "2026-05-18",
    excerpt:
      "记录从一个模糊想法到可运行页面的过程：拆小一点，做慢一点，反而更容易持续。",
    tag: "技术",
    url: "#",
  },
  {
    title: "那些让我停下来看的瞬间",
    date: "2026-05-12",
    excerpt:
      "窗边的光、路上的树影、一本读到一半的书，都是值得被温柔保存的素材。",
    tag: "观察",
    url: "#",
  },
];

const postsList = document.querySelector("#posts-list");

const formatDate = (date) =>
  new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(new Date(date));

const renderPosts = () => {
  postsList.innerHTML = posts
    .map(
      (post) => `
        <article class="post-card">
          <div>
            <div class="post-meta">
              <span class="post-tag">${post.tag}</span>
              <time datetime="${post.date}">${formatDate(post.date)}</time>
            </div>
            <h3>${post.title}</h3>
            <p>${post.excerpt}</p>
          </div>
          <a class="read-more" href="${post.url}" aria-label="阅读文章：${post.title}">
            继续阅读
          </a>
        </article>
      `
    )
    .join("");
};

renderPosts();
